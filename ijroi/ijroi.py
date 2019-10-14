# Copyright: Luis Pedro Coelho <luis@luispedro.org>, 2012
#            Tim D. Smith <git@tim-smith.us>, 2015
# License: MIT

from io import BytesIO
import zipfile

import numpy as np

MAGIC = b'Iout'
SPLINE_FIT = 1
DOUBLE_HEADED = 2
OUTLINE = 4
OVERLAY_LABELS = 8
OVERLAY_NAMES = 16
OVERLAY_BACKGROUNDS = 32
OVERLAY_BOLD = 64
SUB_PIXEL_RESOLUTION = 128
DRAW_OFFSET = 256

# From RoiDecoder.java: "header2 offsets"
# TODO maybe convert to sizes?
C_POSITION = 4
Z_POSITION = 8
T_POSITION = 12
NAME_OFFSET = 16
NAME_LENGTH = 20
OVERLAY_LABEL_COLOR = 24
OVERLAY_FONT_SIZE = 28 # short
AVAILABLE_BYTE1 = 30 # byte
IMAGE_OPACITY = 31 # byte
IMAGE_SIZE = 32 # int
FLOAT_STROKE_WIDTH = 36 # float
ROI_PROPS_OFFSET = 40
ROI_PROPS_LENGTH = 44
COUNTERS_OFFSET = 48


class RoiType:
    POLYGON = 0
    RECT = 1
    OVAL = 2
    LINE = 3
    FREELINE = 4
    POLYLINE = 5
    NOROI = 6
    FREEHAND = 7
    TRACED = 8
    ANGLE = 9
    POINT = 10


def read_roi(fileobj):
    '''
    points = read_roi(fileobj)

    Read ImageJ's ROI format. Points are returned in a nx2 array. Each row
    is in [row, column] -- that is, (y,x) -- order.
    '''
    # This is based on:
    # http://rsbweb.nih.gov/ij/developer/source/ij/io/RoiDecoder.java.html
    # http://rsbweb.nih.gov/ij/developer/source/ij/io/RoiEncoder.java.html
    def get8():
        s = fileobj.read(1)
        if not s:
            raise IOError('readroi: Unexpected EOF')
        return ord(s)

    def get16():
        b0 = get8()
        b1 = get8()
        return (b0 << 8) | b1

    def get32():
        s0 = get16()
        s1 = get16()
        return (s0 << 16) | s1

    def getfloat():
        v = np.int32(get32())
        return v.view(np.float32)

    #===========================================================================
    #Read Header data
    
    magic = fileobj.read(4)
    if magic != MAGIC:
        raise ValueError('Magic number not found')
        
    version = get16()

    # It seems that the roi type field occupies 2 Bytes, but only one is used
    roi_type = get8()
    # Discard second Byte:
    get8()
    
    top = get16()
    left = get16()
    bottom = get16()
    right = get16()
    n_coordinates = get16()
    x1 = getfloat()
    y1 = getfloat()
    x2 = getfloat()
    y2 = getfloat()
    stroke_width = get16()
    shape_roi_size = get32()
    stroke_color = get32()
    fill_color = get32()
    subtype = get16()
    
    options = get16()
    arrow_style = get8()
    arrow_head_size = get8()
    # TODO this always right? looks like this is only written if
    # type == rect (in RoiEncoder.java)
    rect_arc_size = get16()
    position = get32()
    header2offset = get32()

    # TODO delete
    '''
    print('version:', version)
    print('roi_type:', roi_type)
    print('top:', top)
    print('left:', left)
    print('bottom:', bottom)
    print('right:', right)
    print('n_coordinates:', n_coordinates)
    print('x1:', x1)
    print('x2:', x2)
    print('y1:', y1)
    print('y2:', y2)
    print('stroke_width:', stroke_width)
    print('shape_roi_size:', shape_roi_size)
    print('stroke_color:', stroke_color)
    print('fill_color:', fill_color)
    print('subtype:', subtype)
    print('options:', options)
    print('arrow_style:', arrow_style)
    print('arrow_head_size:', arrow_head_size)
    print('rect_arc_size:', rect_arc_size)
    print('position:', position)
    print('header2offset:', header2offset)
    '''
    #

    # End Header data
    #===========================================================================

    #RoiDecoder.java checks the version when setting sub-pixel resolution, therefore so do we
    subPixelResolution = ((options&SUB_PIXEL_RESOLUTION)!=0) and (version>=222)
    
    # Check exceptions
    if roi_type not in [RoiType.FREEHAND, RoiType.TRACED, RoiType.POLYGON,
        RoiType.RECT, RoiType.POINT, RoiType.OVAL]:

        raise NotImplementedError('roireader: ROI type %s not supported' % roi_type)
        
    if subtype != 0:
        raise NotImplementedError('roireader: ROI subtype %s not supported (!= 0)' % subtype)

    if roi_type == RoiType.OVAL:
        if subPixelResolution:
            raise NotImplementedError('roireader: subPixelResolution not '
                'supported for OVAL ROI subtype')
        else:
            # TODO break into which pixels are mostly in the circle / not
            # -> draw polyline roi around them
            # TODO TODO test for off-by-one here
            width = right - left
            height = bottom - top
            rx = width / 2
            ry = height / 2
            center_x = left + rx
            center_y = top + ry
            points = []
            for corner_x in range(left, right + 1):
                for corner_y in range(top, bottom + 1):
                    # TODO maybe don't adjust to "center" of pixel?
                    x = corner_x + 0.5
                    y = corner_y + 0.5
                    if (((x - center_x)**2 / rx**2) + 
                        ((y - center_y)**2 / ry**2)) <= 1.0:
                        # TODO TODO TODO test again. seemed it was transposed...
                        points.append([corner_y, corner_x])

            # TODO TODO TODO for other users of library, trace the edge of this
            # mask to make something like a polyline (to keep return type
            # consistent)
            # (right now return all pixels inside ellipse)
            return np.array(points, dtype=np.int16)
    
    if roi_type == RoiType.RECT:
        if subPixelResolution:
            return np.array(
                [[y1, x1], [y1, x1+x2], [y1+y2, x1+x2], [y1+y2, x1]],
                dtype=np.float32)
        else:
            return np.array(
                [[top, left], [top, right], [bottom, right], [bottom, left]],
                dtype=np.int16)

    if subPixelResolution:
        getc = getfloat
        points = np.empty((n_coordinates, 2), dtype=np.float32)
        fileobj.seek(4*n_coordinates, 1)
    else:
        getc = get16
        points = np.empty((n_coordinates, 2), dtype=np.int16)

    points[:, 1] = [getc() for i in range(n_coordinates)]
    points[:, 0] = [getc() for i in range(n_coordinates)]

    '''
    c_position = get32()
    z_position = get32()
    t_position = get32()
    name_offset = get32()
    name_length = get32()
    overlay_label_color = get32()
    overlay_font_size = get16()
    available_byte1 = get8()
    image_opacity = get8()
    # TODO unsigned?
    image_size = get32()
    float_stroke_width = getfloat()
    roi_props_offset = get32()
    roi_props_length = get32()
    counters_offset = get32()

    # TODO delete
    print('c_position:', c_position)
    print('z_position:', z_position)
    print('t_position:', t_position)
    print('name_offset:', name_offset)
    print('name_length:', name_length)
    print('overlay_label_color:', overlay_label_color)
    print('overlay_font_size:', overlay_font_size)
    print('available_byte1:', available_byte1)
    print('image_opacity:', image_opacity)
    print('image_size:', image_size)
    print('float_stroke_width:', float_stroke_width)
    print('roi_props_offset:', roi_props_offset)
    print('roi_props_length:', roi_props_length)
    print('counters_offset:', counters_offset)

    rest = fileobj.read()
    print('rest:', rest)
    print('type(rest):', type(rest))
    print('len(rest):', len(rest))
    import ipdb; ipdb.set_trace()
    '''
    #

    fileobj.seek(header2offset + NAME_OFFSET)
    name_offset = get32()
    fileobj.seek(header2offset + NAME_LENGTH)
    name_length = get32()

    fileobj.seek(name_offset)
    name = ''
    for _ in range(name_length):
        chr_data = get16()
        name += chr(chr_data)

    if not subPixelResolution:
        points[:, 1] += left
        points[:, 0] += top

    return points


def read_roi_zip(fname):
    with zipfile.ZipFile(fname) as zf:
        return[(n, read_roi(BytesIO(zf.read(n)))) for n in zf.namelist()]


# TODO probably generalize roi repr to a class, s.t. other attributes can be
# encoded, and class can be passed for writing?
def write_roi(points, fileobj, name=None, roi_type=RoiType.POLYGON):
    write_supported_roi_types = (RoiType.POLYGON, RoiType.OVAL)
    if roi_type not in write_supported_roi_types:
        raise NotImplementedError('write only supports roi_types in {}'.format(
            write_supported_roi_types))

    if name is None:
        # TODO randomly generate / make as imagej does
        raise NotImplementedError
    elif type(name) is not str:
        name = str(name)

    need_to_close = False
    if type(fileobj) is str:
        fileobj = open(fileobj, 'wb')
        need_to_close = True

    # TODO correct?
    byteorder = 'big'
    def write_bytes(num, n_bytes, signed=None):
        if signed is None:
            if n_bytes == 2:
                # Just because ImageJ RoiDecoder.java says:
                # "2 byte numbers are big-endian signed shorts"
                # in a comment at the top of the file.
                signed = True
            else:
                signed = False

        fileobj.write(int(num).to_bytes(n_bytes, byteorder=byteorder,
            signed=signed))
        write_bytes.bytes_so_far += n_bytes

    write_bytes.bytes_so_far = 0

    # The version I read from my ImageJ install ~2019-08-10 was 227
    version = 217
    #roi_type = RoiType.POLYGON 
    top, left = np.min(points, axis=0)
    bottom, right = np.max(points, axis=0)
    if roi_type == RoiType.POLYGON:
        points = points.copy()
        # TODO TODO so does this mean this fn is always gonna transpose things?
        points[:, 1] -= left
        points[:, 0] -= top

        n_coordinates = len(points)

    else:
        n_coordinates = 0

    x1 = 0
    y1 = 0
    x2 = 0
    y2 = 0

    stroke_width = 0
    shape_roi_size = 0
    stroke_color = 0
    fill_color = 0
    subtype = 0
    options = 0
    arrow_style = 0
    arrow_head_size = 0
    # TODO actually might only want to do this if the type IS a rect
    rect_arc_size = 0
    # TODO this seems to be the frame (in a txy movie)?
    position = 1

    fileobj.write(MAGIC)

    # TODO define fields / field byte sizes (+types?) centrally
    # use struct library?
    write_bytes(version, 2)

    write_bytes(roi_type, 1)
    # Not used.
    write_bytes(0, 1)

    write_bytes(top, 2)
    write_bytes(left, 2)
    write_bytes(bottom, 2)
    write_bytes(right, 2)
    # TODO this supposed to be 4 in oval/rect case? matter? what is it?
    # 0?
    write_bytes(n_coordinates, 2)

    # int 0 also translates to the float 0 here
    write_bytes(x1, 4)
    write_bytes(y1, 4)
    write_bytes(x2, 4)
    write_bytes(y2, 4)

    write_bytes(stroke_width, 2)
    write_bytes(shape_roi_size, 4)
    write_bytes(stroke_color, 4)
    write_bytes(fill_color, 4)
    write_bytes(subtype, 2)

    write_bytes(options, 2)
    write_bytes(arrow_style, 1)
    write_bytes(arrow_head_size, 1)
    write_bytes(rect_arc_size, 2)
    write_bytes(position, 4)

    # Empirically, with three different polygon ROIs saved from ImageJ, each
    # with a different # points, this seems right.
    # (presumably 4 bytes for magic # at beginning and last 4 bytes for this)
    header2offset = write_bytes.bytes_so_far + 2 * n_coordinates * 2 + 8
    write_bytes(header2offset, 4)

    if roi_type == RoiType.POLYGON:
        for y in points[:, 1]:
            write_bytes(y, 2)

        for x in points[:, 0]:
            write_bytes(x, 2)

    # (filling preceding fields w/ 0)
    write_bytes(0, NAME_OFFSET)
    # TODO calculate this as imagej does (including intermediate fields)
    hardcoded_name_offset = header2offset + COUNTERS_OFFSET + 4
    write_bytes(hardcoded_name_offset, 4)
    write_bytes(len(name), 4)

    # TODO actually fill them in?
    # Zero-ing out other fields.
    curr_header2_byte = 24
    n_bytes_to_zero = hardcoded_name_offset - header2offset - curr_header2_byte
    write_bytes(0, n_bytes_to_zero)

    for c in name:
        # TODO check encoding as a precondition or something?
        write_bytes(ord(c), 2, signed=False)

    if need_to_close:
        fileobj.close()


def write_polygon_roi(points, fileobj, name=None):
    write_roi(points, fileobj, name=name, roi_type=RoiType.POLYGON)
   

def write_roi_zip(name2points, fname, roi_type=RoiType.POLYGON):
    # TODO if calls to write_roi raise NotImplementedError, file that was being
    # written to should be deleted

    # TODO TODO maybe allow names to be autogenerated incrementally?
    # (or get from pandas index if applicable)
    with zipfile.ZipFile(fname, mode='w') as zf:
        for name, points in name2points:
            single_roi_fname = name
            # Otherwise it seems ImageJ won't recognize the ROIs for import.
            if not single_roi_fname.endswith('.roi'):
                single_roi_fname += '.roi'
            f = BytesIO()

            write_roi(points, f, name, roi_type=roi_type)

            zf.writestr(single_roi_fname, f.getvalue())
            f.close()


def write_polygon_roi_zip(name2points, fname):
    write_roi_zip(name2points, fname, roi_type=RoiType.POLYGON)


def write_oval_roi_zip(name2points, fname):
    """Writes oval ROIs from their bounding boxes.
    """
    write_roi_zip(name2points, fname, roi_type=RoiType.OVAL)

