from tkinter import *
from tkinter import ttk

import os

from property_parser import Property
from config import ConfigFile
import utils

voice_item = None

UI = {}
coop_selected = False

TABS_SP = {}
TABS_COOP = {}

def modeswitch_sp():
    global coop_selected
    coop_selected = False
    UI['mode_SP'].state(['disabled'])
    UI['mode_COOP'].state(['!disabled'])
    refresh()
    
def modeswitch_coop():
    global coop_selected
    coop_selected = True
    UI['mode_SP'].state(['!disabled'])
    UI['mode_COOP'].state(['disabled'])
    refresh()
    
def show_trans(e):
    text = UI['trans']
    text['state'] = 'normal'
    text.delete(1.0, END)
    text.insert('end', e.widget.transcript)
    text['state'] = 'disabled'
    
def configure_canv(e):
    canvas = e.widget
    frame = canvas.frame
    canvas['scrollregion'] = (
        0,
        0,
        canvas.winfo_reqwidth(),
        frame.winfo_reqheight(),
        )
    print(canvas.winfo_width())
    frame['width'] = canvas.winfo_width()
    
def save():
    pass
    
def refresh(e=None):
    notebook = UI['tabs']
    is_coop = coop_selected
    
    # Save the current tab index so we can restore it after.
    current_tab = notebook.index(notebook.select())
    
    # Add or remove tabs so only the correct mode is visible.
    for name, tab in sorted(TABS_SP.items()):
        if is_coop:
            notebook.forget(tab)
        else:
            notebook.add(tab)
            notebook.tab(tab, text=tab.nb_text)
            
    for name, tab in sorted(TABS_COOP.items()):
        if is_coop:
            notebook.add(tab)
            notebook.tab(tab, text=tab.nb_text)
        else:
            notebook.forget(tab)
    notebook.select(current_tab)

def init(root):
    '''Initialise all the widgets.'''
    global win
    win = Toplevel(root, name='voiceEditor')
    win.columnconfigure(0, weight=1)
    
    btn_frame = ttk.Frame(win)
    btn_frame.grid(row=0, column=0, sticky='EW')
    btn_frame.columnconfigure(0, weight=1)
    btn_frame.columnconfigure(1, weight=1)
    
    UI['mode_SP'] = ttk.Button(
        btn_frame, 
        text='Single-Player',
        state=['disabled'],
        command=modeswitch_sp,
        )
    UI['mode_SP'].grid(row=0, column=0, sticky=E)
    
    UI['mode_COOP'] = ttk.Button(
        btn_frame, 
        text='Coop',
        command=modeswitch_coop,
        )
    UI['mode_COOP'].grid(row=0, column=1, sticky=W)

    
    pane = ttk.PanedWindow(
        win,
        orient=VERTICAL)
        
    pane.grid(row=1, column=0, sticky='NSEW')
    win.rowconfigure(1, weight=1)
    
    UI['tabs'] = ttk.Notebook(pane, name='notebook')
    UI['tabs'].enable_traversal() # Add keyboard shortcuts
    pane.add(UI['tabs'], weight=2)
    
    trans_frame = ttk.Frame(pane)
    trans_frame.rowconfigure(0, weight=1)
    trans_frame.columnconfigure(0, weight=1)
    pane.add(trans_frame, weight=1)
    
    ttk.Label(
        trans_frame,
        text='Transcript:',
        ).grid(
            row=0,
            column=0, 
            sticky=W,
            )
    
    trans_inner_frame = ttk.Frame(trans_frame, borderwidth=2, relief='sunken')
    trans_inner_frame.grid(row=1, column=0, sticky='NSEW')
    trans_inner_frame.rowconfigure(0, weight=1)
    trans_inner_frame.columnconfigure(0, weight=1)
    
    UI['trans'] = Text(
        trans_inner_frame,
        width=10, 
        height=8,
        wrap='word',
        relief='flat',
        state='disabled',
        font=('Helvectia', 10),
        )
    UI['trans_scroll'] = ttk.Scrollbar(
        trans_inner_frame,
        orient=VERTICAL,
        command=UI['trans'].yview,
        )
    UI['trans']['yscrollcommand'] = UI['trans_scroll'].set
    UI['trans_scroll'].grid(row=0, column=1, sticky='NS')
    UI['trans'].grid(row=0, column=0, sticky='NSEW')
    
    ttk.Button(
        win,
        text='Save',
        command=save,
        ).grid(row=2, column=0)
    
def show(quote_pack):
    '''Display the editing window.'''
    global voice_item, config_sp, config_coop
    voice_item = quote_pack
    
    notebook = UI['tabs']
    
    quote_data = quote_pack.config
    
    os.makedirs('config/voice', exist_ok=True)
    config_sp = ConfigFile('voice/SP_' + quote_pack.id + '.cfg')
    config_coop = ConfigFile('voice/COOP_' + quote_pack.id + '.cfg')
    
    # Destroy all the old tabs
    for tab in TABS_SP.values():
        notebook.forget(tab)
        tab.destroy()
    for tab in TABS_COOP.values():
        notebook.forget(tab)
        tab.destroy()
    TABS_SP.clear()
    TABS_COOP.clear()
    
    make_tabs(quote_data.find_key('quotes_sp'), TABS_SP, config_sp, 'sp')
    make_tabs(quote_data.find_key('quotes_coop'), TABS_COOP, config_coop, 'coop')
    config_sp.save()
    config_coop.save()
    
    refresh()
    win.deiconify()
    win.lift(win.winfo_parent())

def make_tabs(props, tab_dict, config, mode):
    '''Create all the widgets for a tab.'''
    for group in props.find_all('Group'):
        group_name = group['name']
        group_desc = group['desc', '']
        print(group_name, group_desc)
        # This is just to hold the canvas and scrollbar
        outer_frame = ttk.Frame(UI['tabs'])
        outer_frame.columnconfigure(0, weight=1)
        outer_frame.rowconfigure(0, weight=1)
        
        tab_dict[group_name] = outer_frame
        # We add this attribute so the refresh() method knows all the 
        # tab names
        outer_frame.nb_text = group_name
        
        
        # We need a canvas to make the list scrollable.
        canv = Canvas(
            outer_frame, 
            highlightthickness=0,
            name=mode + '_' + group_name + '_canv',
            )
        scroll = ttk.Scrollbar(
        outer_frame,
        orient=VERTICAL,
        command=canv.yview,
        )
        canv['yscrollcommand'] = scroll.set
        canv.grid(row=0, column=0, sticky='NSEW')
        scroll.grid(row=0, column=1, sticky='NS')
        
        UI['tabs'].add(outer_frame)
        
        
        # This holds the actual elements
        frame = ttk.Frame(
            canv, 
            name=mode + '_' + group_name + '_frame',
            )
        frame.columnconfigure(0, weight=1)
        canv.create_window(0, 0, window=frame, anchor="nw")
        
        # We do this so we can adjust the scrollregion later in 
        # <Configure>.
        canv.frame = frame
        
        ttk.Label(
            frame,
            text=group_name,
            anchor='center',
            font='tkHeadingFont',
            ).grid(
                row=0, 
                column=0, 
                sticky='EW',
                )
                
        ttk.Label(
            frame,
            text=group_desc + ':',
            ).grid(
                row=1, 
                column=0, 
                sticky='EW',
                )
                
        ttk.Separator(frame, orient=HORIZONTAL).grid(
            row=2,
            column=0,
            sticky='EW',
            )
            
        for quote in group.find_all('Quote'):
            ttk.Label(
                frame, 
                text=quote['name'],
                ).grid(
                    column=0,
                    sticky=W,
                    )
            
            for line in quote.find_all('Instance'):
                line_id = line['id', line['name']]
                check = ttk.Checkbutton(    
                    frame,
                    text=line['name'],
                    )
                check.quote_var = IntVar(
                    value=config.get_bool(group_name, line_id, True),
                    )
                check.transcript = '\n'.join(
                    ['"' + trans.value + '"'
                    for trans in
                    line.find_all('trans')
                    ])
                check['variable'] = check.quote_var
                check.grid(
                    column=0,
                    padx=(10, 0),
                    sticky=W,
                    )
                check.bind("<Enter>", show_trans) 
        canv.bind('<Configure>', configure_canv)


if __name__ == '__main__':
    import packageLoader
    data = packageLoader.load_packages('packages\\', False)

    root = Tk()
    ttk.Label(root, text='Root Window').grid()
    init(root)
    d = {quote.id: quote for quote in data['QuotePack']}
    print(d)
    show(d['BEE2_CAVE_50s'])