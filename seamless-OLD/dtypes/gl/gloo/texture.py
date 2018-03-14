# -*- coding: utf-8 -*-
#
# Taken and adapted from vispy/gloo/texture.py
# -----------------------------------------------------------------------------
# Copyright (c) 2015, Vispy Development Team. All Rights Reserved.
# Modifications: (c) 2017 Sjoerd de Vries. All Rights Reserved.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
# -----------------------------------------------------------------------------

import math

import numpy as np
string_types = (str, bytes)


def check_enum(enum, name=None, valid=None):
    """ Get lowercase string representation of enum.
    """
    name = name or 'enum'
    # Try to convert
    res = None
    if isinstance(enum, int):
        if hasattr(enum, 'name') and enum.name.startswith('GL_'):
            res = enum.name[3:].lower()
    elif isinstance(enum, string_types):
        res = enum.lower()
    # Check
    if res is None:
        raise ValueError('Could not determine string represenatation for'
                         'enum %r' % enum)
    elif valid and res not in valid:
        raise ValueError('Value of %s must be one of %r, not %r' %
                         (name, valid, enum))
    return res


class GLObject:
    pass

# ----------------------------------------------------------- Texture class ---
class BaseTexture(GLObject):
    """
    A Texture is used to represent a topological set of scalar values.

    Parameters
    ----------
    gltexstore: gltexstore

    data : ndarray | tuple | None
        Texture data in the form of a numpy array (or something that
        can be turned into one). A tuple with the shape of the texture
        can also be given.
    format : str | enum | None
        The format of the texture: 'luminance', 'alpha',
        'luminance_alpha', 'rgb', or 'rgba'. If not given the format
        is chosen automatically based on the number of channels.
        When the data has one channel, 'luminance' is assumed.
    resizable : bool
        Indicates whether texture can be resized. Default True.
    interpolation : str | None
        Interpolation mode, must be one of: 'nearest', 'linear'.
        Default 'nearest'.
    wrapping : str | None
        Wrapping mode, must be one of: 'repeat', 'clamp_to_edge',
        'mirrored_repeat'. Default 'clamp_to_edge'.
    shape : tuple | None
        Optional. A tuple with the shape of the texture. If ``data``
        is also a tuple, it will override the value of ``shape``.
    internalformat : str | None
        Internal format to use.
    """
    _ndim = 2

    _formats = {
        1: 'luminance',  # or alpha, or red
        2: 'luminance_alpha',  # or rg
        3: 'rgb',
        4: 'rgba'
    }

    _inv_formats = {
        'luminance': 1,
        'alpha': 1,
        'red': 1,
        'luminance_alpha': 2,
        'rg': 2,
        'rgb': 3,
        'rgba': 4
    }

    _inv_internalformats = dict([
        (base + suffix, channels)
        for base, channels in [('r', 1), ('rg', 2), ('rgb', 3), ('rgba', 4)]
        for suffix in ['8', '16', '16f', '32f']
    ] + [
        ('luminance', 1),
        ('alpha', 1),
        ('red', 1),
        ('luminance_alpha', 2),
        ('rg', 2),
        ('rgb', 3),
        ('rgba', 4)
    ])

    _gltexstore = None
    def __init__(self, gltexstore,
                 data=None, format=None, resizable=True,
                 interpolation=None, wrapping=None, shape=None,
                 internalformat=None):


        assert gltexstore is not None
        self._gltexstore = gltexstore

        # Init shape and format
        self._resizable = True  # at least while we're in init
        self._shape = tuple([0 for i in range(self._ndim+1)])
        self._format = format
        self._internalformat = internalformat

        # Set texture parameters (before setting data)
        self.interpolation = interpolation or 'nearest'
        self.wrapping = wrapping or 'clamp_to_edge'

        # Set data or shape (shape arg is for backward compat)
        if isinstance(data, tuple):
            shape, data = data, None
        if data is not None:
            if shape is not None:
                raise ValueError('Texture needs data or shape, not both.')
            data = np.array(data, copy=False)
            # So we can test the combination
            self._resize(data.shape, format, internalformat)
            self._set_data(data)
        elif shape is not None:
            self._resize(shape, format, internalformat)
        else:
            raise ValueError("Either data or shape must be given")

        # Set resizable (at end of init)
        self._resizable = bool(resizable)

    def _normalize_shape(self, data_or_shape):
        # Get data and shape from input
        if isinstance(data_or_shape, np.ndarray):
            data = data_or_shape
            shape = data.shape
        else:
            assert isinstance(data_or_shape, tuple)
            data = None
            shape = data_or_shape
        # Check and correct
        if shape:
            if len(shape) < self._ndim:
                raise ValueError("Too few dimensions for texture")
            elif len(shape) > self._ndim + 1:
                raise ValueError("Too many dimensions for texture")
            elif len(shape) == self._ndim:
                shape = shape + (1,)
            else:  # if len(shape) == self._ndim + 1:
                if shape[-1] > 4:
                    raise ValueError("Too many channels for texture")
        # Return
        return data.reshape(shape) if data is not None else shape

    @property
    def shape(self):
        """ Data shape (last dimension indicates number of color channels)
        """
        return self._shape

    @property
    def format(self):
        """ The texture format (color channels).
        """
        return self._format

    @property
    def wrapping(self):
        """ Texture wrapping mode """
        value = self._wrapping
        return value[0] if all([v == value[0] for v in value]) else value

    @wrapping.setter
    def wrapping(self, value):
        # Convert
        if isinstance(value, int) or isinstance(value, string_types):
            value = (value,) * self._ndim
        elif isinstance(value, (tuple, list)):
            if len(value) != self._ndim:
                raise ValueError('Texture wrapping needs 1 or %i values' %
                                 self._ndim)
        else:
            raise ValueError('Invalid value for wrapping: %r' % value)
        # Check and set
        valid = 'repeat', 'clamp_to_edge', 'mirrored_repeat'
        value = tuple([check_enum(value[i], 'tex wrapping', valid)
                       for i in range(self._ndim)])
        self._wrapping = value
        assert self._gltexstore is not None
        self._gltexstore.set_wrapping(value)

    @property
    def interpolation(self):
        """ Texture interpolation for minification and magnification. """
        value = self._interpolation
        return value[0] if value[0] == value[1] else value

    @interpolation.setter
    def interpolation(self, value):
        # Convert
        if isinstance(value, int) or isinstance(value, string_types):
            value = (value,) * 2
        elif isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise ValueError('Texture interpolation needs 1 or 2 values')
        else:
            raise ValueError('Invalid value for interpolation: %r' % value)
        # Check and set
        valid = 'nearest', 'linear'
        value = (check_enum(value[0], 'tex interpolation', valid),
                 check_enum(value[1], 'tex interpolation', valid))
        self._interpolation = value
        assert self._gltexstore is not None
        self._gltexstore.set_interpolation(*value)

    def resize(self, shape, format=None, internalformat=None):
        """Set the texture size and format

        Parameters
        ----------
        shape : tuple of integers
            New texture shape in zyx order. Optionally, an extra dimention
            may be specified to indicate the number of color channels.
        format : str | enum | None
            The format of the texture: 'luminance', 'alpha',
            'luminance_alpha', 'rgb', or 'rgba'. If not given the format
            is chosen automatically based on the number of channels.
            When the data has one channel, 'luminance' is assumed.
        internalformat : str | enum | None
            The internal (storage) format of the texture: 'luminance',
            'alpha', 'r8', 'r16', 'r16f', 'r32f'; 'luminance_alpha',
            'rg8', 'rg16', 'rg16f', 'rg32f'; 'rgb', 'rgb8', 'rgb16',
            'rgb16f', 'rgb32f'; 'rgba', 'rgba8', 'rgba16', 'rgba16f',
            'rgba32f'.  If None, the internalformat is chosen
            automatically based on the number of channels.  This is a
            hint which may be ignored by the OpenGL implementation.
        """
        return self._resize(shape, format, internalformat)

    def _resize(self, shape, format=None, internalformat=None):
        """Internal method for resize.
        """
        shape = self._normalize_shape(shape)

        # Check
        if not self._resizable:
            raise RuntimeError("Texture is not resizable")

        # Determine format
        if format is None:
            format = self._formats[shape[-1]]
            # Keep current format if channels match
            if self._format and \
               self._inv_formats[self._format] == self._inv_formats[format]:
                format = self._format
        else:
            format = check_enum(format)

        if internalformat is None:
            # Keep current internalformat if channels match
            if self._internalformat and \
               self._inv_internalformats[self._internalformat] == shape[-1]:
                internalformat = self._internalformat
        else:

            internalformat = check_enum(internalformat)

        # Check
        if format not in self._inv_formats:
            raise ValueError('Invalid texture format: %r.' % format)
        elif shape[-1] != self._inv_formats[format]:
            raise ValueError('Format does not match with given shape. '
                             '(format expects %d elements, data has %d)' %
                             (self._inv_formats[format], shape[-1]))

        if internalformat is None:
            pass
        elif internalformat not in self._inv_internalformats:
            raise ValueError(
                'Invalid texture internalformat: %r. Allowed formats: %r'
                % (internalformat, self._inv_internalformats)
            )
        elif shape[-1] != self._inv_internalformats[internalformat]:
            raise ValueError('Internalformat does not match with given shape.')

        # Store and send GLIR command
        self._shape = shape
        self._format = format
        self._internalformat = internalformat
        assert self._gltexstore is not None
        # signed or unsigned byte? In the Vispy GLIR texture implementation,
        # this is inconsistent: signed for 1D and 3D textures, unsigned for 2D?
        # for now, always use unsigned bytes...
        self._gltexstore.set_size(self._shape, self._format,
                           self._internalformat, unsigned=True)

    def set_data(self, data, offset=None, copy=False):
        """Set texture data

        Parameters
        ----------
        data : ndarray
            Data to be uploaded
        offset: int | tuple of ints
            Offset in texture where to start copying data
        copy: bool
            Since the operation is deferred, data may change before
            data is actually uploaded to GPU memory. Asking explicitly
            for a copy will prevent this behavior.

        Notes
        -----
        This operation implicitly resizes the texture to the shape of
        the data if given offset is None.
        """
        return self._set_data(data, offset, copy)

    def _set_data(self, data, offset=None, copy=False):
        """Internal method for set_data.
        """

        # Copy if needed, check/normalize shape
        data = np.array(data, copy=copy)
        data = self._normalize_shape(data)

        # Maybe resize to purge DATA commands?
        if offset is None:
            self._resize(data.shape)
        elif all([i == 0 for i in offset]) and data.shape == self._shape:
            self._resize(data.shape)

        # Convert offset to something usable
        offset = offset or tuple([0 for i in range(self._ndim)])
        assert len(offset) == self._ndim

        # Check if data fits
        for i in range(len(data.shape)-1):
            if offset[i] + data.shape[i] > self._shape[i]:
                raise ValueError("Data is too large")

        assert self._gltexstore is not None
        self._gltexstore.set_data(offset, data)

    def __setitem__(self, key, data):
        """ x.__getitem__(y) <==> x[y] """

        # Make sure key is a tuple
        if isinstance(key, (int, slice)) or key == Ellipsis:
            key = (key,)

        # Default is to access the whole texture
        shape = self._shape
        slices = [slice(0, shape[i]) for i in range(len(shape))]

        # Check last key/Ellipsis to decide on the order
        keys = key[::+1]
        dims = range(0, len(key))
        if key[0] == Ellipsis:
            keys = key[::-1]
            dims = range(len(self._shape) - 1,
                         len(self._shape) - 1 - len(keys), -1)

        # Find exact range for each key
        for k, dim in zip(keys, dims):
            size = self._shape[dim]
            if isinstance(k, int):
                if k < 0:
                    k += size
                if k < 0 or k > size:
                    raise IndexError("Texture assignment index out of range")
                start, stop = k, k + 1
                slices[dim] = slice(start, stop, 1)
            elif isinstance(k, slice):
                start, stop, step = k.indices(size)
                if step != 1:
                    raise IndexError("Cannot access non-contiguous data")
                if stop < start:
                    start, stop = stop, start
                slices[dim] = slice(start, stop, step)
            elif k == Ellipsis:
                pass
            else:
                raise TypeError("Texture indices must be integers")

        offset = tuple([s.start for s in slices])[:self._ndim]
        shape = tuple([s.stop - s.start for s in slices])
        size = np.prod(shape) if len(shape) > 0 else 1

        # Make sure data is an array
        if not isinstance(data, np.ndarray):
            data = np.array(data, copy=False)
        # Make sure data is big enough
        if data.shape != shape:
            data = np.resize(data, shape)

        # Set data (deferred)
        self._set_data(data=data, offset=offset, copy=False)

    def __repr__(self):
        return "<%s shape=%r format=%r at 0x%x>" % (
            self.__class__.__name__, self._shape, self._format, id(self))


# --------------------------------------------------------- Texture1D class ---
class Texture1D(BaseTexture):
    """ One dimensional texture

    Parameters
    ----------
    data : ndarray | tuple | None
        Texture data in the form of a numpy array (or something that
        can be turned into one). A tuple with the shape of the texture
        can also be given.
    format : str | enum | None
        The format of the texture: 'luminance', 'alpha',
        'luminance_alpha', 'rgb', or 'rgba'. If not given the format
        is chosen automatically based on the number of channels.
        When the data has one channel, 'luminance' is assumed.
    resizable : bool
        Indicates whether texture can be resized. Default True.
    interpolation : str | None
        Interpolation mode, must be one of: 'nearest', 'linear'.
        Default 'nearest'.
    wrapping : str | None
        Wrapping mode, must be one of: 'repeat', 'clamp_to_edge',
        'mirrored_repeat'. Default 'clamp_to_edge'.
    shape : tuple | None
        Optional. A tuple with the shape of the texture. If ``data``
        is also a tuple, it will override the value of ``shape``.
    internalformat : str | None
        Internal format to use.
    """
    _ndim = 1
    _GLIR_TYPE = 'Texture1D'

    @property
    def width(self):
        """ Texture width """
        return self._shape[0]

    @property
    def glsl_type(self):
        """ GLSL declaration strings required for a variable to hold this data.
        """
        return 'uniform', 'sampler1D'

    @property
    def glsl_sampler_type(self):
        """ GLSL type of the sampler.
        """
        return 'sampler1D'

    @property
    def glsl_sample(self):
        """ GLSL function that samples the texture.
        """
        return 'texture1D'


# --------------------------------------------------------- Texture2D class ---
class Texture2D(BaseTexture):
    """ Two dimensional texture

    Parameters
    ----------
    data : ndarray
        Texture data shaped as W, or a tuple with the shape for
        the texture (W).
    format : str | enum | None
        The format of the texture: 'luminance', 'alpha',
        'luminance_alpha', 'rgb', or 'rgba'. If not given the format
        is chosen automatically based on the number of channels.
        When the data has one channel, 'luminance' is assumed.
    resizable : bool
        Indicates whether texture can be resized. Default True.
    interpolation : str
        Interpolation mode, must be one of: 'nearest', 'linear'.
        Default 'nearest'.
    wrapping : str
        Wrapping mode, must be one of: 'repeat', 'clamp_to_edge',
        'mirrored_repeat'. Default 'clamp_to_edge'.
    shape : tuple
        Optional. A tuple with the shape HxW. If ``data``
        is also a tuple, it will override the value of ``shape``.
    internalformat : str | None
        Internal format to use.
    """
    _ndim = 2
    _GLIR_TYPE = 'Texture2D'

    @property
    def height(self):
        """ Texture height """
        return self._shape[0]

    @property
    def width(self):
        """ Texture width """
        return self._shape[1]

    @property
    def glsl_type(self):
        """ GLSL declaration strings required for a variable to hold this data.
        """
        return 'uniform', 'sampler2D'

    @property
    def glsl_sampler_type(self):
        """ GLSL type of the sampler.
        """
        return 'sampler2D'

    @property
    def glsl_sample(self):
        """ GLSL function that samples the texture.
        """
        return 'texture2D'


# --------------------------------------------------------- Texture3D class ---
class Texture3D(BaseTexture):
    """ Three dimensional texture

    Parameters
    ----------
    data : ndarray | tuple | None
        Texture data in the form of a numpy array (or something that
        can be turned into one). A tuple with the shape of the texture
        can also be given.
    format : str | enum | None
        The format of the texture: 'luminance', 'alpha',
        'luminance_alpha', 'rgb', or 'rgba'. If not given the format
        is chosen automatically based on the number of channels.
        When the data has one channel, 'luminance' is assumed.
    resizable : bool
        Indicates whether texture can be resized. Default True.
    interpolation : str | None
        Interpolation mode, must be one of: 'nearest', 'linear'.
        Default 'nearest'.
    wrapping : str | None
        Wrapping mode, must be one of: 'repeat', 'clamp_to_edge',
        'mirrored_repeat'. Default 'clamp_to_edge'.
    shape : tuple | None
        Optional. A tuple with the shape of the texture. If ``data``
        is also a tuple, it will override the value of ``shape``.
    internalformat : str | None
        Internal format to use.
    """
    _ndim = 3
    _GLIR_TYPE = 'Texture3D'

    @property
    def width(self):
        """ Texture width """
        return self._shape[2]

    @property
    def height(self):
        """ Texture height """
        return self._shape[1]

    @property
    def depth(self):
        """ Texture depth """
        return self._shape[0]

    @property
    def glsl_type(self):
        """ GLSL declaration strings required for a variable to hold this data.
        """
        return 'uniform', 'sampler3D'

    @property
    def glsl_sampler_type(self):
        """ GLSL type of the sampler.
        """
        return 'sampler3D'

    @property
    def glsl_sample(self):
        """ GLSL function that samples the texture.
        """
        return 'texture3D'
