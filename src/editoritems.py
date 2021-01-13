"""Parses the Puzzlemaker's item format."""
from enum import Enum, auto
from typing import (
    Optional, Type, Callable, NamedTuple,
    List, Dict, Tuple, Set,
    Iterable, IO, Iterator, Collection,
)
from pathlib import PurePosixPath as FSPath

from srctools import Vec, logger, conv_int, conv_bool
from srctools.tokenizer import Tokenizer, Token
from editoritems_props import ItemProp, PROP_TYPES


LOGGER = logger.get_logger(__name__)


class ItemClass(Enum):
    """PeTI item classes."""
    # Value: (ID, instance count, models per subitem)

    # Default
    UNCLASSED = ('ItemBase', 1, 1)

    FLOOR_BUTTON = ('ItemButtonFloor', 6, 1)
    PEDESTAL_BUTTON = ('ItemPedestalButton', 1, 1)

    PANEL_STAIR = 'ItemStairs', 1, 2
    PANEL_FLIP = 'ItemPanelFlip', 1, 1

    # Both glass and panel items
    PANEL_ANGLED = 'ItemAngledPanel', 1, 12
    PISTON_PLATFORM = 'ItemPistonPlatform', 1, 7
    TRACK_PLATFORM = 'ItemRailPlatform', 6, 3

    CUBE = 'ItemCube', 5, 2
    GEL = PAINT = 'ItemPaintSplat', 1, 1
    FAITH_PLATE = 'ItemCatapult', 1, 1

    CUBE_DROPPER = 'ItemCubeDropper', 1, 1
    GEL_DROPPER = PAINT_DROPPER = 'ItemPaintDropper', 1, 1
    FAITH_TARGET = 'ItemCatapultTarget', 1, 1

    # Input-less items
    GLASS = 'ItemBarrier', 9, 1
    TURRET = 'ItemTurret', 1, 1
    LIGHT_STRIP = 'ItemLightStrip', 1, 1
    GOO = 'ItemGoo', 0, 2

    # Items with inputs
    LASER_EMITTER = 'ItemLaserEmitter', 1, 1
    FUNNEL = 'ItemTBeam', 3, 1
    FIZZLER = 'ItemBarrierHazard', 2, 1
    LIGHT_BRIDGE = 'ItemLightBridge', 1, 1

    # Extent/handle pseudo-items
    HANDLE_FIZZLER = 'ItemBarrierHazardExtent', 0, 1
    HANDLE_GLASS = 'ItemBarrierExtent', 0, 1
    HANDLE_PISTON_PLATFORM = 'ItemPistonPlatformExtent', 0, 1
    HANDLE_TRACK_PLATFORM = 'ItemRailPlatformExtent', 0, 1

    # Entry/Exit corridors
    DOOR_ENTRY_SP = 'ItemEntranceDoor', 12, 1
    DOOR_ENTRY_COOP = 'ItemCoopEntranceDoor', 5, 1
    DOOR_EXIT_SP = 'ItemExitDoor', 6, 2
    DOOR_EXIT_COOP = 'ItemCoopExitDoor', 6, 2

    @property
    def id(self) -> str:
        """The ID used in the configs."""
        return self.value[0]

    @property
    def inst_count(self) -> int:
        """The number of intances items of this type have, at maximum."""
        return self.value[1]

    @property
    def models_per_subtype(self) -> int:
        """The number of models to provide for each subtype."""
        return self.value[2]


CLASS_BY_NAME = {
    itemclass.id.casefold(): itemclass
    for itemclass in ItemClass
}


class RenderableType(Enum):
    """The two "renderables", which show up in their own block."""
    ERROR = 'ErrorState'
    CONN = 'ConnectionHeartSolid'


class Handle(Enum):
    """Types of directional handles."""
    NONE = 'HANDLE_NONE'
    QUAD = 'HANDLE_4_DIRECTIONS'  # 4 directions
    CENT_OFF = 'HANDLE_5_POSITIONS'  # Center, 4 offsets
    DUAL_OFF = 'HANDLE_6_POSITIONS'  # 4 offsets, center in 2 directions
    QUAD_OFF = 'HANDLE_8_POSITIONS'  # 4 directions, center and offset each
    FREE_ROT = 'HANDLE_36_DIRECTIONS'  # 10 degree increments on floor
    FAITH = 'HANDLE_CATAPULT'  # Faith Plate


class Surface(Enum):
    """Used for InvalidSurface."""
    WALL = WALLS = 'WALL'
    FLOOR = 'FLOOR'
    CEIL = CEILING = 'CEILING'


class DesiredFacing(Enum):
    """Items automatically reorient when moved around."""
    NONE = 'DESIRES_ANYTHING'  # Doesn't care.
    POSX = UP = 'DESIRES_UP'  # Point +x upward.
    NEGX = DN = DOWN = 'DESIRES_DOWN'  # Point -x upward.
    HORIZ = HORIZONTAL = 'DESIRES_HORIZONTAL'  # Point y axis up, either way.


class FaceType(Enum):
    """Types of surfaces produced by EmbedFace."""
    NORMAL = 'Grid_Default'  # Whatever normally appears.
    HALF_VERT = '2x1'  # Half-vertical white.
    LRG = FULL = '1x1'
    MED = HALF = '2x2'
    SML = QUAD = '4x4'
    CHECK = CHECKERED = '4x4_checkered'


class CollType(Enum):
    """Types of collisions between items."""
    GRATE = GRATING = auto()
    GLASS = auto()
    BRIDGE = auto()
    FIZZLER = auto()
    PHYSICS = auto()
    ANTLINES = auto()
    NOTHING = auto()
    EVERYTHING = auto()


class Sound(Enum):
    """Events which trigger a sound."""
    SELECT = 'SOUND_SELECTED'
    DESELECT = 'SOUND_DESELECTED'
    DELETE = 'SOUND_DELETED'
    CREATE = 'SOUND_CREATED'
    PROPS_OPEN = 'SOUND_EDITING_ACTIVATE'
    PROPS_CLOSE = 'SOUND_EDITING_DEACTIVATE'


class Anim(Enum):
    """Maps events to sequence indexes for the editor models.

    Most of these are used for the special cube behaviour.
    Flat there is on the floor without a dropper, fall is for the midair pose
    with a dropper.
    """
    IDLE = 'ANIM_IDLE'

    EDIT_START = 'ANIM_EDITING_ACTIVATE'
    EDIT_STOP = 'ANIM_EDITING_DEACTIVATE'

    CUBE_FLAT = IDLE
    CUBE_FLAT_EDIT_START = EDIT_START
    CUBE_FLAT_EDIT_STOP = EDIT_STOP

    CUBE_FALL = 'ANIM_FALLING_IDLE'
    CUBE_FALL_EDIT_START = 'ANIM_FALLING_EDITING_ACTIVATE'
    CUBE_FALL_EDIT_STOP = 'ANIM_FALLING_EDITING_DEACTIVATE'
    CUBE_FLAT2FALL = 'ANIM_GROUND_TO_FALLING'
    CUBE_FALL2FLAT = 'ANIM_FALLING_TO_GROUND'
    CUBE_FLAT2FALL_EDIT = 'ANIM_GROUND_TO_FALLING_EDITING'
    CUBE_FALL2FLAT_EDIT = 'ANIM_FALLING_TO_GROUND_EDITING'

    CDROP_ENABLE = 'ANIM_REAPPEAR'
    CDROP_DISABLE = 'ANIM_DISAPPEAR'

    # Connection heart icon:
    HEART_IDLE = 'ANIM_ICON_HEART_HAPPY_IDLE'
    HEART_CONN_MADE = 'ANIM_ICON_HEART_SUCCESS'
    HEART_CONN_BROKE = 'ANIM_ICON_HEART_BREAK'

    # Invalid-placement icon:
    BAD_PLACE_IDLE = 'ANIM_ICON_IDLE'
    BAD_PLACE_SHOW = 'ANIM_ICON_SHOW'
    BAD_PLACE_HIDE = 'ANIM_ICON_HIDE'

    @classmethod
    def parse_block(cls, anims: Dict['Anim', int], tok: Tokenizer) -> None:
        """Parse a block of animation definitions."""
        for anim_name in tok.block('Animations'):
            try:
                anim = Anim(anim_name)
            except ValueError:
                raise tok.error('Unknown animation {}', anim_name) from None
            anims[anim] = conv_int(tok.expect(Token.STRING))


class ConnTypes(Enum):
    """Input/output types. Many of these are used to link item pairs."""
    NORMAL = IO = 'CONNECTION_STANDARD'  # Normal input/output
    POLARITY = 'CONNECTION_TBEAM_POLARITY'

    CUBE_DROPPER = BOX_DROPPER = 'CONNECTION_BOX_DROPPER'
    GEL_DROPPER = PAINT_DROPPER = 'CONNECTION_PAINT_DROPPER'
    BARRIER = 'CONNECTION_BARRIER_ANCHOR_TO_EXTENT'

    FIZZ_BRUSH = 'CONNECTION_HAZARD_BRUSH'
    FIZZ_MODEL = 'CONNECTION_HAZARD_MODEL'  # Broken open/close input.
    FIZZ = 'CONNECTION_HAZARD'  # Output from base.


class InstCount(NamedTuple):
    """Instances have several associated counts."""
    inst: FSPath  # The actual filename.
    ent_count: int
    brush_count: int
    face_count: int


class Coord(NamedTuple):
    """Integer coordinates."""
    x: int
    y: int
    z: int

    @classmethod
    def parse(cls, value: str, error_func: Callable[..., BaseException]) -> 'Coord':
        """Parse from a string, using the function to raise errors."""
        parts = value.split()
        if len(parts) != 3:
            raise error_func('Incorrect number of points for a coordinate!')
        try:
            x = int(parts[0])
        except ValueError:
            raise error_func('Invalid coordinate value "{}"!', parts[0])
        try:
            y = int(parts[1])
        except ValueError:
            raise error_func('Invalid coordinate value "{}"!', parts[1])
        try:
            z = int(parts[2])
        except ValueError:
            raise error_func('Invalid coordinate value "{}"!', parts[2])
        try:
            return _coord_cache[x, y, z]
        except KeyError:
            result = cls(x, y, z)
            _coord_cache[result] = result
            return result


class EmbedFace(NamedTuple):
    """A face generated by the editor."""
    center: Vec  # Center point, Z always is 128.
    size: Vec  # Size of the tile.
    type: FaceType  # Surface material.


class Overlay(NamedTuple):
    """An overlay placed by the editor on the ground."""
    material: str  # Material to show.
    center: Vec  # Center point.
    size: Vec  # Size of the overlay.
    rotation: int  # Orientation of the overlay.


# Cache these coordinates, since most items are going to be near the origin.
_coord_cache: Dict[Tuple[int, int, int], Coord] = {}

ITEM_CLASSES: Dict[str, ItemClass] = {
    cls.id.casefold(): cls
    for cls in ItemClass
}
FACE_TYPES: Dict[str, FaceType] = {
    face.value.casefold(): face
    for face in FaceType
}

# The defaults, if this is unset.
DEFAULT_ANIMS = {
    Anim.IDLE: 0,
    Anim.EDIT_START: 1,
    Anim.EDIT_STOP: 2,
}
DEFAULT_SOUNDS = {
    Sound.SELECT: '',
    Sound.DESELECT: '',

    Sound.PROPS_OPEN: 'P2Editor.ExpandOther',
    Sound.PROPS_CLOSE: 'P2Editor.CollapseOther',

    Sound.CREATE: 'P2Editor.PlaceOther',
    Sound.DELETE: 'P2Editor.RemoveOther',
}


class ConnSide(Enum):
    """Sides of an item, where antlines connect to."""
    LEFT = Coord(1, 0, 0)
    RIGHT = Coord(-1, 0, 0)
    UP = Coord(0, 1, 0)
    DOWN = Coord(0, -1, 0)

    @classmethod
    def parse(cls, value: str, error_func: Callable[..., BaseException]) -> 'ConnSide':
        """Parse a connection side."""
        try:
            return cls[value.upper()]
        except KeyError:
            pass
        parts = value.split()
        if len(parts) != 3:
            raise error_func('Incorrect number of points for a direction!')
        try:
            x, y, z = map(int, parts)
        except ValueError:
            raise error_func('Invalid connection side!')
        if z != 0:
            raise error_func('Connection side must be flat!')
        if x == 0:
            if y == 1:
                return ConnSide.UP
            elif y == -1:
                return ConnSide.DOWN
        elif y == 0:
            if x == 1:
                return ConnSide.LEFT
            elif x == -1:
                return ConnSide.RIGHT
        raise error_func('Unknown connection side ({}, {}, 0)', x, y)


class AntlinePoint(NamedTuple):
    """Locations antlines can connect to."""
    pos: Coord
    sign_off: Coord
    priority: int
    group: Optional[int]


def bounding_boxes(voxels: Iterable[Coord]) -> Iterator[Tuple[Coord, Coord]]:
    """Decompose a bunch of points into a small list of bounding boxes enclosing them.

    This is used to determine a good set of Volume definitions to write out.
    """
    # To compute the volume, pick a random point still to be done, then
    # expand as far as possible in each direction.
    EXTENT = 50
    todo = set(voxels)
    while todo:
        x1, y1, z1 = x2, y2, z2 = todo.pop()
        # X+:
        for x in range(x1 + 1, x1 + EXTENT):
            if (x, y1, z1) in todo:
                x2 = x
            else:
                break
        # X-:
        for x in range(x1 - 1, x1 - EXTENT, -1):
            if (x, y1, z1) in todo:
                x1 = x
            else:
                break

        # Y+:
        for y in range(y1 + 1, y1 + EXTENT):
            if all((x, y, z1) in todo for x in range(x1, x2+1)):
                y2 = y
            else:
                break

        # Y-:
        for y in range(y1 - 1, y1 - EXTENT, -1):
            if all((x, y, z1) in todo for x in range(x1, x2+1)):
                y1 = y
            else:
                break

        # Y+:
        for z in range(z1 + 1, z1 + EXTENT):
            if all((x, y, z) in todo for x in range(x1, x2+1) for y in range(y1, y2+1)):
                z2 = z
            else:
                break

        # Y-:
        for z in range(z1 - 1, z1 - EXTENT, -1):
            if all((x, y, z) in todo for x in range(x1, x2+1) for y in range(y1, y2+1)):
                z1 = z
            else:
                break

        for x in range(x1, x2+1):
            for y in range(y1, y2+1):
                for z in range(z1, z2+1):
                    todo.discard(Coord(x, y, z))
        yield Coord(x1, y1, z1), Coord(x2, y2, z2)


class Renderable:
    """Simpler definition used for the heart and error icons."""
    _types = {r.value.casefold(): r for r in RenderableType}
    def __init__(
        self,
        typ: RenderableType,
        model: str,
        animations: Dict[Anim, int],
    ):
        self.type = typ
        self.model = model
        self.animations = animations

    @classmethod
    def parse(cls, tok: Tokenizer) -> 'Renderable':
        """Parse a renderable."""
        kind: Optional[RenderableType] = None
        model = ''
        anims = {}

        for key in tok.block("Renderable Item"):
            if key.casefold() == "type":
                render_id = tok.expect(Token.STRING)
                try:
                    kind = cls._types[render_id.casefold()]
                except KeyError:
                    raise tok.error('Unknown Renderable "{}"!', render_id)
            elif key.casefold() == "animations":
                Anim.parse_block(anims, tok)
            elif key.casefold() == "model":
                model = tok.expect(Token.STRING)
            else:
                raise tok.error('Unknown renderable option "{}"!', key)
        if kind is None:
            raise tok.error('No type specified for Renderable!')
        return Renderable(kind, model, anims)


class SubType:
    """Represents a single sub-item component of an overall item.

    Should not be constructed directly.
    """
    # The name, shown on remove connection windows.
    name: str
    # The models this uses, in order. The editoritems format includes
    # a texture name for each of these, but it's never used.
    models: List[FSPath]
    # For each sound type, the soundscript to use.
    sounds: Dict[Sound, str]
    # For each animation category, the sequence index.
    anims: Dict[Anim, int]

    # The capitalised name to display in the bottom of the palette window.
    # If not on the palette, set to ''.
    pal_name: str
    # X/Y position on the palette, or None if not on the palette
    pal_pos: Optional[Tuple[int, int]]
    # The path to the icon VTF, in 'models/props_map_editor'.
    pal_icon: Optional[FSPath]

    def __init__(
        self,
        name: str,
        models: List[FSPath],
        sounds: Dict[Sound, str],
        anims: Dict[Anim, int],
        pal_name: str,
        pal_pos: Optional[Tuple[int, int]],
        pal_icon: Optional[FSPath],
    ) -> None:
        self.name = name
        self.models = models
        self.sounds = sounds
        self.anims = anims
        self.pal_name = pal_name
        self.pal_pos = pal_pos
        self.pal_icon = pal_icon

    @classmethod
    def parse(cls, tok: Tokenizer) -> 'SubType':
        """Parse a subtype from editoritems."""
        subtype: SubType = cls('', [], DEFAULT_SOUNDS.copy(), {}, '', None, None)
        for key in tok.block('Subtype'):
            folded_key = key.casefold()
            if folded_key == 'name':
                subtype.name = tok.expect(Token.STRING)
            elif folded_key == 'model':
                # In the original file this is a block, but allow a name
                # since the texture is unused.
                token, tok_value = next(tok.skipping_newlines())
                model_name: Optional[FSPath] = None
                if token is Token.STRING:
                    model_name = FSPath(tok_value)
                elif token is Token.BRACE_OPEN:
                    # Parse the block.
                    for subkey in tok.block('Model', consume_brace=False):
                        subkey = subkey.casefold()
                        if subkey == 'modelname':
                            model_name = FSPath(tok.expect(Token.STRING))
                        elif subkey == 'texturename':
                            tok.expect(Token.STRING)  # Skip this.
                        else:
                            raise tok.error('Unknown model option "{}"!', subkey)
                else:
                    raise tok.error(token)
                if model_name is None:
                    raise tok.error('No model name specified!')
                if model_name.suffix.casefold() != '.mdl':
                    # Swap to '.mdl', since that's what the real model is.
                    model_name = model_name.with_suffix('.mdl')
                subtype.models.append(model_name)
            elif folded_key == 'palette':
                for subkey in tok.block('Palette'):
                    subkey = subkey.casefold()
                    if subkey == 'tooltip':
                        subtype.pal_name = tok.expect(Token.STRING)
                    elif subkey == 'image':
                        subtype.pal_icon = FSPath(tok.expect(Token.STRING))
                    elif subkey == 'position':
                        points = tok.expect(Token.STRING).split()
                        if len(points) in (2, 3):
                            try:
                                x = int(points[0])
                                y = int(points[1])
                            except ValueError:
                                raise tok.error('Invalid position value!') from None
                        else:
                            raise tok.error('Incorrect number of points in position') from None
                        subtype.pal_pos = x, y
                    else:
                        raise tok.error('Unknown palette option "{}"!', subkey)
            elif folded_key == 'sounds':
                for sound_kind in tok.block('Sounds'):
                    try:
                        sound = Sound(sound_kind.upper())
                    except ValueError:
                        raise tok.error('Unknown sound type "{}"!', sound_kind)
                    subtype.sounds[sound] = tok.expect(Token.STRING)
            elif folded_key == 'animations':
                Anim.parse_block(subtype.anims, tok)
            else:
                raise tok.error('Unknown subtype option "{}"!', key)
        return subtype

    def export(self, f: IO[str]) -> None:
        """Write the subtype to a file."""
        f.write('\t\t"Subtype"\n\t\t\t{\n')
        if self.name:
            f.write(f'\t\t\t"Name" "{self.name}"\n')
        for model in self.models:
            # It has to be a .3ds file, even though it's really MDL.
            model = model.with_suffix('.3ds')
            f.write(f'\t\t\t"Model" {{ "ModelName" "{model}" }}\n')
        if self.pal_pos is not None:
            f.write('\t\t\t"Palette"\n\t\t\t\t{\n')
            f.write(f'\t\t\t\t"Tooltip"  "{self.pal_name}"\n')
            if self.pal_icon is not None:
                # Similarly needs to be PNG even though it's really VTF.
                pal_icon = self.pal_icon.with_suffix('.png')
                f.write(f'\t\t\t\t"Image"    "{pal_icon}"\n')
            x, y = self.pal_pos
            f.write(f'\t\t\t\t"Position" "{x} {y} 0"\n')
            f.write('\t\t\t\t}\n')
        if self.sounds != DEFAULT_SOUNDS:
            f.write('\t\t\t"Sounds"\n\t\t\t\t{\n')
            for snd_type in Sound:
                try:
                    sndscript = self.sounds[snd_type]
                except KeyError:
                    continue
                f.write(f'\t\t\t\t"{snd_type.value}" "{sndscript}"\n')
            f.write('\t\t\t\t}\n')
        if self.anims:
            f.write('\t\t\t"Sounds"\n\t\t\t\t{\n')
            for anim_name, anim_ind in sorted(self.anims.items(), key=lambda t: t[1]):
                f.write(f'\t\t\t\t"{anim_name.value}" "{anim_ind}"\n')
            f.write('\t\t\t\t}\n')
        f.write('\t\t\t}\n')


class Item:
    """A specific item."""
    id: str  # The item's unique ID.
    # The C++ class used to instantiate the item in the editor.
    cls: ItemClass
    subtype_prop: Optional[Type[ItemProp]]
    # Movement handle
    handle: Handle
    facing: DesiredFacing
    invalid_surf: Set[Surface]
    animations: Dict[Anim, int]  # Anim name to sequence index.

    anchor_barriers: bool
    anchor_goo: bool
    occupies_voxel: bool
    copiable: bool
    deletable: bool

    subtypes: List[SubType]  # Each subtype in order.

    def __init__(
        self,
        item_id: str,
        cls: ItemClass,
        subtype_prop: Optional[Type[ItemProp]] = None,
        movement_handle: Handle = Handle.NONE,
        desired_facing: DesiredFacing = DesiredFacing.NONE,
        invalid_surf: Iterable[Surface] = (),
        anchor_on_barriers: bool = False,
        anchor_on_goo: bool = False,
        occupies_voxel: bool = True
    ) -> None:
        self.animations = {}
        self.id = item_id
        self.cls = cls
        self.subtype_prop = subtype_prop
        self.subtypes = []
        self.properties: Dict[str, ItemProp] = {}
        self.handle = movement_handle
        self.facing = desired_facing
        self.invalid_surf = set(invalid_surf)
        self.anchor_barriers = anchor_on_barriers
        self.anchor_goo = anchor_on_goo
        self.occupies_voxel = occupies_voxel
        self.copiable = True
        self.deletable = True
        self.pseduo_handle = False
        # The default is 0 0 0, but this isn't useful since the rotation point
        # is wrong. So just make it the useful default, users can override.
        self.offset = Vec(64, 64, 64)
        self.targetname = ''

        # The instances used by the editor, then custom slots used by
        # conditions. For the latter we don't care about the counts.
        self.instances: List[InstCount] = []
        self.cust_instances: Dict[str, FSPath] = {}
        self.antline_points: Dict[ConnSide, List[AntlinePoint]] = {
            side: [] for side in ConnSide
        }
        # The voxels this hollows out inside the floor.
        self.embed_voxels: Set[Coord] = set()
        # Brushes automatically created
        self.embed_faces: List[EmbedFace] = []
        # Overlays automatically placed
        self.overlays: List[Overlay] = []

    @classmethod
    def parse(cls, file: Iterable[str], filename: Optional[str] = None) -> Tuple[Dict[str, 'Item'], Dict[RenderableType, Renderable]]:
        """Parse an entire editoritems file."""
        items: Dict[str, Item] = {}
        icons: Dict[RenderableType, Renderable] = {}
        tok = Tokenizer(file, filename)

        if tok.expect(Token.STRING).casefold() != 'itemdata':
            raise tok.error('No "ItemData" block present!')

        for key in tok.block('ItemData'):
            if key.casefold() == 'item':
                it = cls.parse_one(tok)
                if it.id in items:
                    LOGGER.warning('Item {} redeclared!', it.id)
                items[it.id] = it
            elif key.casefold() == 'renderables':
                for render_block in tok.block('Renderables'):
                    if render_block.casefold() != 'item':
                        raise tok.error('Unknown block "{}"!', render_block)
                    ico = Renderable.parse(tok)
                    icons[ico.type] = ico
            else:
                raise tok.error('Unknown block "{}"!', key)

        return items, icons

    @classmethod
    def parse_one(cls, tok: Tokenizer) -> 'Item':
        """Parse an item.

        This expects the "Item" token to have been read already.
        """
        tok.expect(Token.BRACE_OPEN)
        item: Item = cls('', ItemClass.UNCLASSED)

        for token, tok_value in tok:
            if token is Token.BRACE_CLOSE:
                # Done, check we're not missing critical stuff.
                if not item.id:
                    raise tok.error('No item ID (Type) set!')
                return item
            elif token is Token.NEWLINE:
                continue
            elif token is not Token.STRING:
                raise tok.error(token)
            tok_value = tok_value.casefold()
            if tok_value == 'type':
                if item.id:
                    raise tok.error('Item ID (Type) set multiple times!')
                item.id = tok.expect(Token.STRING).upper()
                if not item.id:
                    raise tok.error('Invalid item ID (Type) "{}"', item.id)
            elif tok_value == 'itemclass':
                item_class = tok.expect(Token.STRING)
                try:
                    item.cls = ITEM_CLASSES[item_class.casefold()]
                except KeyError:
                    raise tok.error('Unknown item class {}!', item_class)
            elif tok_value == 'editor':
                item._parse_editor_block(tok)
            elif tok_value == 'properties':
                item._parse_properties_block(tok)
            elif tok_value == 'exporting':
                item._parse_export_block(tok)
            elif tok_value in ('author', 'description', 'filter'):
                # These are BEE2.2 values, which are not used.
                tok.expect(Token.STRING)
            else:
                raise tok.error('Unexpected item option "{}"!', tok_value)

        raise tok.error('File ended without closing item block!')

    # Boolean option in editor -> Item attribute.
    _BOOL_ATTRS = {
        'cananchoronbarriers': 'anchor_barriers',
        'cananchorongoo': 'anchor_barriers',
        'occupiesvoxel': 'occupies_voxel',
        'copyable': 'copiable',
        'deletable': 'deletable',
        'pseudohandle': 'pseudo_handle',
    }

    def _parse_editor_block(self, tok: Tokenizer) -> None:
        """Parse the editor block of the item definitions."""
        for key in tok.block('Editor'):
            folded_key = key.casefold()
            if folded_key == 'subtype':
                self.subtypes.append(SubType.parse(tok))
            elif folded_key == 'animations':
                Anim.parse_block(self.animations, tok)
            elif folded_key == 'movementhandle':
                handle_str = tok.expect(Token.STRING)
                try:
                    self.handle = Handle(handle_str.upper())
                except ValueError:
                    raise tok.error('Unknown handle type {}', handle_str)
            elif folded_key == 'invalidsurface':
                for word in tok.expect(Token.STRING).split():
                    try:
                        self.invalid_surf.add(Surface[word.upper()])
                    except KeyError:
                        raise tok.error('Unknown surface type {}', word)
            elif folded_key == 'subtypeproperty':
                subtype_prop = tok.expect(Token.STRING)
                try:
                    self.subtype_prop = PROP_TYPES[subtype_prop.casefold()]
                except ValueError:
                    raise tok.error('Unknown property {}', subtype_prop)
            elif folded_key == 'desiredfacing':
                desired_facing = tok.expect(Token.STRING)
                try:
                    self.facing = DesiredFacing(desired_facing.upper())
                except ValueError:
                    raise tok.error('Unknown desired facing {}', desired_facing)
            elif folded_key == 'rendercolor':
                # Rendercolor is on catapult targets, and is useless.
                tok.expect(Token.STRING)
            else:
                try:
                    attr = self._BOOL_ATTRS[folded_key]
                except KeyError:
                    raise tok.error('Unknown editor option {}', key)
                else:
                    setattr(self, attr, conv_bool(tok.expect(Token.STRING)))

    def _parse_properties_block(self, tok: Tokenizer) -> None:
        """Parse the properties block of the item definitions."""
        for prop_str in tok.block('Properties'):
            try:
                prop_type = PROP_TYPES[prop_str.casefold()]
            except KeyError:
                raise tok.error(f'Unknown property "{prop_str}"!')

            default = ''
            index = 0
            user_default = True
            for prop_value in tok.block(prop_str + ' options'):
                prop_value = prop_value.casefold()
                if prop_value == 'defaultvalue':
                    default = tok.expect(Token.STRING)
                elif prop_value == 'index':
                    index = conv_int(tok.expect(Token.STRING))
                elif prop_value == 'bee2_ignore':
                    user_default = conv_bool(tok.expect(Token.STRING), user_default)
                else:
                    raise tok.error('Unknown property option "{}"!', prop_value)
            try:
                self.properties[prop_type.id] = prop_type(default, index, user_default)
            except ValueError:
                raise tok.error('Default value {} is not valid for {} properties!', default, prop_type.id)

    def _parse_export_block(self, tok: Tokenizer) -> None:
        """Parse the export block of the item definitions."""
        for key in tok.block('Exporting'):
            folded_key = key.casefold()
            if folded_key == 'targetname':
                self.targetname = tok.expect(Token.STRING)
            elif folded_key == 'offset':
                self.offset = Vec.from_str(tok.expect(Token.STRING))
            elif folded_key == 'instances':
                # We allow several syntaxes for instances, since the counts are
                # pretty useless. Instances can be defined by position (for originals),
                # or by name for use in conditions.
                for inst_name in tok.block('Instance'):
                    self._parse_instance_block(tok, inst_name)
            elif folded_key == 'connectionpoints':
                self._parse_connection_points(tok)
            elif folded_key == 'embeddedvoxels':
                self._parse_embedded_voxels(tok)
            elif folded_key == 'embedface':
                self._parse_embed_faces(tok)
            elif folded_key == 'overlay':
                self._parse_overlay(tok)
            else:  # TODO: Temp, skip over other blocks.
                # raise tok.error('Unknown export option "{}"!', key)
                level = 0
                for token, tok_value in tok:
                    if token is Token.BRACE_OPEN:
                        level += 1
                    elif token is Token.BRACE_CLOSE:
                        level -= 1
                        if level <= 0:
                            break

    def _parse_instance_block(self, tok: Tokenizer, inst_name: str) -> None:
        """Parse a section in the instances block."""
        inst_ind: Optional[int]
        inst_file: Optional[str]
        try:
            inst_ind = int(inst_name)
        except ValueError:
            inst_ind = None
            if inst_name.casefold().startswith('bee2_'):
                inst_name = inst_name[5:]
            else:
                LOGGER.warning(
                    'Custom instance names should have bee2_ prefix (line '
                    '{}, file {})',
                    tok.line_num, tok.filename)
        else:
            # Add blank spots if this is past the end.
            while inst_ind > len(self.instances):
                self.instances.append(InstCount(FSPath(), 0, 0, 0))
        block_tok, inst_file = next(tok.skipping_newlines())
        if block_tok is Token.BRACE_OPEN:
            ent_count = brush_count = side_count = 0
            inst_file = None
            for block_key in tok.block('Instances', consume_brace=False):
                folded_key = block_key.casefold()
                if folded_key == 'name':
                    inst_file = tok.expect(Token.STRING)
                elif folded_key == 'entitycount':
                    ent_count = conv_int(tok.expect(Token.STRING))
                elif folded_key == 'brushcount':
                    brush_count = conv_int(tok.expect(Token.STRING))
                elif folded_key == 'brushsidecount':
                    side_count = conv_int(tok.expect(Token.STRING))
                else:
                    raise tok.error('Unknown instance option {}', block_key)
            if inst_file is None:
                raise tok.error('No instance filename provided!')
            inst = InstCount(FSPath(inst_file), ent_count, brush_count,
                             side_count)
        elif block_tok is Token.STRING:
            inst = InstCount(FSPath(inst_file), 0, 0, 0)
        else:
            raise tok.error(block_tok)
        if inst_ind is not None:
            if inst_ind == len(self.instances):
                self.instances.append(inst)
            else:
                self.instances[inst_ind] = inst
        else:
            self.cust_instances[inst_name] = inst.inst

    def _parse_connection_points(self, tok: Tokenizer) -> None:
        for point_key in tok.block('ConnectionPoints'):
            if point_key.casefold() != 'point':
                raise tok.error('Unknown connection point "{}"!', point_key)
            direction: Optional[ConnSide] = None
            pos: Optional[Coord] = None
            sign_pos: Optional[Coord] = None
            group_id: Optional[int] = None
            priority = 0
            for conn_key in tok.block('Point'):
                folded_key = conn_key.casefold()
                if folded_key == 'dir':
                    direction = ConnSide.parse(tok.expect(Token.STRING), tok.error)
                elif folded_key == 'pos':
                    pos = Coord.parse(tok.expect(Token.STRING), tok.error)
                elif folded_key == 'signageoffset':
                    sign_pos = Coord.parse(tok.expect(Token.STRING), tok.error)
                elif folded_key == 'priority':
                    priority = conv_int(tok.expect(Token.STRING))
                elif folded_key == 'groupid':
                    group_id = conv_int(tok.expect(Token.STRING))
                else:
                    raise tok.error('Unknown point option "{}"!', folded_key)
            if direction is None:
                raise tok.error('No direction for connection point!')
            if pos is None:
                raise tok.error('No position for connection point!')
            if sign_pos is None:
                raise tok.error('No signage position for connection point!')
            self.antline_points[direction].append(AntlinePoint(pos, sign_pos, priority, group_id))

    def _parse_embedded_voxels(self, tok: Tokenizer) -> None:
        # There are two definition types here - a single voxel, or a whole bbox.
        for embed_key in tok.block('EmbeddedVoxels'):
            folded_key = embed_key.casefold()
            if folded_key == 'volume':
                pos_1: Optional[Coord] = None
                pos_2: Optional[Coord] = None
                for pos_key in tok.block('EmbeddedVolume'):
                    if pos_key.casefold() == 'pos1':
                        pos_1 = Coord.parse(tok.expect(Token.STRING), tok.error)
                    elif pos_key.casefold() == 'pos2':
                        pos_2 = Coord.parse(tok.expect(Token.STRING), tok.error)
                    else:
                        raise tok.error('Unknown volume key "{}"!', pos_key)
                if pos_1 is None or pos_2 is None:
                    raise tok.error('Missing coordinate for volume!')
                vol_x = range(min(pos_1.x, pos_2.x), max(pos_1.x, pos_2.x) + 1)
                vol_y = range(min(pos_1.y, pos_2.y), max(pos_1.y, pos_2.y) + 1)
                vol_z = range(min(pos_1.z, pos_2.z), max(pos_1.z, pos_2.z) + 1)
                for x in vol_x:
                    for y in vol_y:
                        for z in vol_z:
                            self.embed_voxels.add(Coord(x, y, z))
            elif folded_key == 'voxel':
                # A single position.
                for pos_key in tok.block('EmbeddedVoxel'):
                    if pos_key.casefold() == 'pos':
                        self.embed_voxels.add(Coord.parse(
                            tok.expect(Token.STRING),
                            tok.error,
                        ))
                    else:
                        raise tok.error('Unknown voxel key "{}"!', pos_key)

    def _parse_embed_faces(self, tok: Tokenizer) -> None:
        """Parse embedFace definitions, which add additional brushes to the item."""
        for solid_key in tok.block('EmbedFace'):
            if solid_key.casefold() != 'solid':
                raise tok.error('Unknown Embed Face type "{}"!', solid_key)
            center: Optional[Vec] = None
            size: Optional[Vec] = None
            grid = FaceType.NORMAL
            for opt_key in tok.block('Solid'):
                folded_key = opt_key.casefold()
                if folded_key == 'center':
                    center = Vec.from_str(tok.expect(Token.STRING))
                elif folded_key == 'dimensions':
                    size = Vec.from_str(tok.expect(Token.STRING))
                elif folded_key == 'grid':
                    grid_str = tok.expect(Token.STRING)
                    try:
                        grid = FACE_TYPES[grid_str.casefold()]
                    except KeyError:
                        raise tok.error('Unknown face type "{}"!', grid_str)
                else:
                    raise tok.error('Unknown Embed Face option "{}"!', opt_key)
            if center is None:
                raise tok.error('No position specified for embedded face!')
            if size is None:
                raise tok.error('No size specified for embedded face!')
            self.embed_faces.append(EmbedFace(center, size, grid))

    def _parse_overlay(self, tok: Tokenizer) -> None:
        """Parse overlay definitions, which place overlays."""
        center: Optional[Vec] = None
        size: Optional[Vec] = None
        material = ''
        rotation = 0
        for opt_key in tok.block('Overlay'):
            folded_key = opt_key.casefold()
            if folded_key == 'center':
                center = Vec.from_str(tok.expect(Token.STRING))
            elif folded_key == 'dimensions':
                size = Vec.from_str(tok.expect(Token.STRING))
            elif folded_key == 'material':
                material = tok.expect(Token.STRING)
            elif folded_key == 'rotation':
                rotation = conv_int(tok.expect(Token.STRING))
            else:
                raise tok.error('Unknown Overlay option "{}"!', opt_key)
        if center is None:
            raise tok.error('No position specified for overlay!')
        if size is None:
            raise tok.error('No size specified for overlay!')
        self.overlays.append(Overlay(material, center, size, rotation))

    def export_one(self, f: IO[str]) -> None:
        """Write a single item out to a file."""
        f.write('"Item"\n\t{\n')
        if self.cls is not ItemClass.UNCLASSED:
            f.write(f'\t"Type"      "{self.id}"\n')
            f.write(f'\t"ItemClass" "{self.cls.id}"\n')
        else:
            f.write(f'\t"Type" "{self.id}"\n')
        f.write('\t"Editor"\n\t\t{\n')
        if self.subtype_prop is not None:
            f.write(f'\t\t"SubtypeProperty" "{self.subtype_prop.id}"\n')
        for subtype in self.subtypes:
            subtype.export(f)
        f.write(f'\t\t"MovementHandle" "{self.handle.value}"\n')
        f.write(f'\t\t"OccupiesVoxel"  "{"1" if self.occupies_voxel else "0"}"\n')

        if self.facing is not DesiredFacing.NONE:
            f.write(f'\t\t"DesiredFacing"  "{self.facing.value}"\n')

        if self.invalid_surf:
            invalid = ' '.join(sorted(surf.value for surf in self.invalid_surf))
            f.write(f'\t\t"InvalidSurface" "{invalid}"\n')

        if self.anchor_goo:
            f.write(f'\t\t"CanAnchorOnGoo"      "1"\n')
        if self.anchor_barriers:
            f.write(f'\t\t"CanAnchorOnBarriers" "1"\n')
        if not self.copiable:
            f.write(f'\t\t"Copyable"  "0"\n')
        if not self.deletable:
            f.write(f'\t\t"Deletable" "0"\n')
        if self.pseduo_handle:
            f.write(f'\t\t"PseudoHandle" "1"\n')
        f.write('\t\t}\n')

        if self.properties:
            f.write('\t"Properties"\n\t\t{\n')
            for prop in self.properties.values():
                f.write(f'\t\t"{prop.id}"\n\t\t\t{{\n')
                f.write(f'\t\t\t"DefaultValue" "{prop.export()}"\n')
                f.write(f'\t\t\t"Index"        "{prop.index}"\n')
                f.write('\t\t\t}\n')
            f.write('\t\t}\n')
        f.write('\t"Exporting"\n\t\t{\n')
        if self.instances:
            f.write('\t\t"Instances"\n\t\t\t{\n')
            for i, inst in enumerate(self.instances):
                f.write(f'\t\t\t"{i}"\n\t\t\t\t{{\n')
                file = inst.inst
                if inst.inst == FSPath():
                    f.write('\t\t\t\t"Name" ""\n')
                elif inst.ent_count or inst.brush_count or inst.face_count:
                    f.write(f'\t\t\t\t"Name"           "{file}"\n')
                    f.write(f'\t\t\t\t"EntityCount"    "{inst.ent_count}"\n')
                    f.write(f'\t\t\t\t"BrushCount"     "{inst.brush_count}"\n')
                    f.write(f'\t\t\t\t"BrushSideCount" "{inst.face_count}"\n')
                else:
                    f.write(f'\t\t\t\t"Name" "{file}"\n')
                f.write('\t\t\t\t}\n')
            f.write('\t\t\t}\n')

        if self.targetname:
            f.write(f'\t\t"Targetname" "{self.targetname}"\n')
        f.write(f'\t\t"Offset"     "{self.offset}"\n')

        if self.embed_voxels:
            f.write('\t\t"EmbeddedVoxels"\n\t\t\t{\n')
            for pos1, pos2 in bounding_boxes(self.embed_voxels):
                if pos1 == pos2:
                    f.write('\t\t\t"Voxel"\n\t\t\t\t{\n')
                    f.write(f'\t\t\t\t"Pos" "{pos1.x} {pos1.y} {pos1.z}"\n')
                else:
                    f.write('\t\t\t"Volume"\n\t\t\t\t{\n')
                    f.write(f'\t\t\t\t"Pos1" "{pos1.x} {pos1.y} {pos1.z}"\n')
                    f.write(f'\t\t\t\t"Pos2" "{pos2.x} {pos2.y} {pos2.z}"\n')
                f.write('\t\t\t\t}\n')
            f.write('\t\t\t}\n')

        if self.embed_faces:
            f.write('\t\t"EmbedFace"\n\t\t\t{\n')
            for face in self.embed_faces:
                f.write('\t\t\t"Solid"\n\t\t\t\t{\n')
                f.write(f'\t\t\t\t"Center"     "{face.center}"\n')
                f.write(f'\t\t\t\t"Dimensions" "{face.size}"\n')
                f.write(f'\t\t\t\t"Grid"       "{face.type.value}"\n')
                f.write('\t\t\t\t}\n')
            f.write('\t\t\t}\n')

        for over in self.overlays:
            f.write('\t\t"Overlay"\n\t\t\t{\n')
            f.write(f'\t\t\t"Material"   "{over.material}"\n')
            f.write(f'\t\t\t"Center"     "{over.center}"\n')
            f.write(f'\t\t\t"Dimensions" "{over.size}"\n')
            f.write(f'\t\t\t"Rotation"   "{over.rotation}"\n')
            f.write('\t\t\t}\n')

        if any(self.antline_points.values()):
            f.write('\t\t"ConnectionPoints"\n\t\t\t{\n')
            is_first = True
            for side in ConnSide:
                points = self.antline_points[side]
                if not points:
                    continue
                # Newline between sections.
                if not is_first:
                    f.write('\n')
                is_first = False
                # Recreate Valve's comments around the points, because we can.
                f.write(f'\t\t\t// {side.name.title()}\n')

                for point in points:
                    f.write('\t\t\t"Point"\n\t\t\t\t{\n')
                    f.write(f'\t\t\t\t"Dir"           "{side.value.x} {side.value.y} {side.value.z}"\n')
                    f.write(f'\t\t\t\t"Pos"           "{point.pos.x} {point.pos.y} {point.pos.z}"\n')
                    f.write(f'\t\t\t\t"SignageOffset" "{point.sign_off.x} {point.sign_off.y} {point.sign_off.z}"\n')
                    f.write(f'\t\t\t\t"Priority"      "{point.priority}"\n')
                    if point.group is not None:
                        f.write(f'\t\t\t\t"GroupID"       "{point.group}"\n')
                    f.write('\t\t\t\t}\n')
            f.write('\t\t\t}\n')
        f.write('\t\t}\n')
        f.write('\t}\n')