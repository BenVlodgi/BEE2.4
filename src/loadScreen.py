"""Displays a loading menu while packages, palettes, etc are being loaded.

All the actual display is done in a subprocess, so we can allow interaction while
the main process is busy loading.

The id() of the main-process object is used to identify loadscreens.
"""
from tkinter import *
from tk_tools import TK_ROOT
from tkinter import ttk

from weakref import WeakSet
from abc import abstractmethod
import contextlib
import multiprocessing

from loadScreen_daemon import run_screen as _splash_daemon
from BEE2_config import GEN_OPTS
import utils

from typing import Set, Tuple


# Keep a reference to all loading screens, so we can close them globally.
_ALL_SCREENS = WeakSet()  # type: Set[LoadScreen]

# For each loadscreen ID, record if the cancel button was pressed. We then raise
# Cancelled upon the next interaction with it to stop operation.
_SCREEN_CANCEL_FLAG = {}

# Pairs of pipe ends we use to send data to the daemon and vice versa.
# DAEMON is sent over to the other process.
_PIPE_MAIN_REC, _PIPE_DAEMON_SEND = multiprocessing.Pipe(duplex=False)
_PIPE_DAEMON_REC, _PIPE_MAIN_SEND = multiprocessing.Pipe(duplex=False)


class Cancelled(SystemExit):
    """Raised when the user cancels the loadscreen."""

LOGGER = utils.getLogger(__name__)


def close_all():
    """Hide all loadscreen windows."""
    for screen in _ALL_SCREENS:
        screen.reset()


def show_main_loader():
    """Special function, which sets the splash screen compactness."""
    main_loader._send_msg(
        'set_is_compact',
        GEN_OPTS.get_bool('General', 'compact_splash'),
    )
    main_loader.show()


@contextlib.contextmanager
def surpress_screens():
    """A context manager to surpress loadscreens while the body is active."""
    active = []
    for screen in _ALL_SCREENS:
        if not screen.active:
            continue
        screen.suppress()
        screen.active = False
        active.append(screen)

    yield

    for screen in active:
        screen.unsuppress()
        screen.active = True


def patch_tk_dialogs():
    """Patch various tk windows to hide loading screens while they're are open.

    """
    from tkinter import commondialog

    # contextlib managers can also be used as decorators.
    supressor = surpress_screens()  # type: contextlib.ContextDecorator
    # Messageboxes, file dialogs and colorchooser all inherit from Dialog,
    # so patching .show() will fix them all.
    commondialog.Dialog.show = supressor(commondialog.Dialog.show)

patch_tk_dialogs()


class LoadScreen:
    """LoadScreens show a loading screen for items.

    stages should be (id, title) pairs for each screen stage.
    Each stage can be stepped independently, referenced by the given ID.
    The title can be blank.
    """

    def __init__(self, *stages: Tuple[str, str], title_text: str, is_splash: bool=False):
        self.stages = list(stages)
        self.labels = {}
        self.bar_val = {}
        self.maxes = {}

        self.active = False
        # active determines whether the screen is on, and if False stops most
        # functions from doing anything

        _ALL_SCREENS.add(self)

        # Order the daemon to make this screen.
        _SCREEN_CANCEL_FLAG[id(self)] = False
        self._send_msg('init', is_splash, title_text, stages)

    def __enter__(self):
        """LoadScreen can be used as a context manager.

        Inside the block, the screen will be visible. Cancelling will exit
        to the end of the with block.
        """
        self.show()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Hide the loading screen, and passthrough execptions.
        """
        self.reset()
        # When cancelled, suppress that.
        return exc_type is Cancelled

    def _send_msg(self, command, *args):
        """Send a message to the daemon."""
        _PIPE_MAIN_SEND.send((command, id(self), args))
        # Check the messages coming back as well.
        while _PIPE_MAIN_REC.poll():
            command, arg = _PIPE_MAIN_REC.recv()
            if command == 'main_toggle':
                # Save the compact state to the config.
                GEN_OPTS['General']['compact_splash'] = '1' if arg else '0'
            elif command == 'cancel':
                # Mark this loadscreen as cancelled.
                _SCREEN_CANCEL_FLAG[arg] = True

        # If the flag was set for us, raise an exception - the loading thing
        # will then stop.
        if _SCREEN_CANCEL_FLAG[id(self)]:
            _SCREEN_CANCEL_FLAG[id(self)] = False
            raise Cancelled

    def set_length(self, stage: str, num: int):
        """Set the maximum value for the specified stage."""
        self._send_msg('set_length', stage, num)

    def step(self, stage: str):
        """Increment the specified stage."""
        self._send_msg('step', stage)

    def skip_stage(self, stage: str):
        """Skip over this stage of the loading process."""
        self._send_msg('skip_stage', stage)

    def show(self):
        """Display the loading screen."""
        self._send_msg('reset')
        self._send_msg('show')

    def reset(self):
        """Hide the loading screen and reset all the progress bars."""
        self._send_msg('reset')

    def destroy(self):
        """Permanently destroy this screen and cleanup."""
        self._send_msg('destroy')
        _ALL_SCREENS.remove(self)

    @abstractmethod
    def suppress(self):
        """Temporarily hide the screen."""
        self._send_msg('hide')

    @abstractmethod
    def unsuppress(self):
        """Undo temporarily hiding the screen."""
        self._send_msg('show')


class OldScreen:

    def set_nums(self, stage):
        """Set the fraction text for a stage."""
        max_val = self.maxes[stage]
        if max_val == 0:  # 0/0 sections are skipped automatically.
            self.bar_var[stage].set(1000)
        else:
            self.bar_var[stage].set(
                1000 * self.bar_val[stage] / max_val
            )
        self.labels[stage]['text'] = '{!s}/{!s}'.format(
            self.bar_val[stage],
            max_val,
        )

    def reset(self):
        """Hide the loading screen, and reset stages to zero."""
        self.withdraw()
        self.active = False
        for stage, _ in self.stages:
            self.maxes[stage] = 10
            self.bar_val[stage] = 0
            self.bar_var[stage].set(0)
            self.labels[stage]['text'] = '0/??'
            self.set_nums(stage)

    def destroy(self):
        """Delete all parts of the loading screen."""
        if self.active:
            super().destroy()
            del self.widgets
            del self.maxes
            del self.bar_var
            del self.bar_val
            self.active = False
            _ALL_SCREENS.discard(self)

    def suppress(self):
        """Temporarily hide the screen."""
        self.withdraw()

    def unsuppress(self):
        """Undo temporarily hiding the screen."""
        self.deiconify()


# Initialise the daemon.
_daemon = multiprocessing.Process(
    target=_splash_daemon,
    args=(
        _PIPE_DAEMON_SEND,
        _PIPE_DAEMON_REC,
        # Pass translation strings.
        {
            'skip': _('Skipped!'),
            'version': _('Version: ') + utils.BEE_VERSION,
        }
    ),
    name='loadscreen_daemon',
)
# Destroy when we quit.
_daemon.daemon = True
_daemon.start()

main_loader = LoadScreen(
    ('PAK', _('Packages')),
    ('OBJ', _('Loading Objects')),
    ('IMG', _('Loading Images')),
    ('UI', _('Initialising UI')),
    title_text=_('Better Extended Editor for Portal 2'),
    is_splash=True,
)