"""Minimal read-only GeoTIFF / Cloud-Optimized GeoTIFF tile reader (ABB-12, HLS).

Reads only what CropStory needs from HLS v2.0 COGs: the full-resolution image (first IFD) of a
single-band, tiled, little- or big-endian classic TIFF, uncompressed or Deflate-compressed, with
or without horizontal differencing (predictor 2), plus the GeoTIFF georeferencing of a UTM
(EPSG 326xx/327xx) raster. Anything else is rejected with ``GeoTiffError`` instead of being
guessed. The standard library is enough for this, so no GDAL/rasterio dependency is added
(ADR-0009).

The layout is checked against the structure observed in live HLS files on 2026-11-15:
3660 × 3660 px, 256 × 256 tiles, Deflate, predictor 2, int16 bands / uint8 Fmask, 30 m pixels.
"""
from __future__ import annotations

import math
import struct
import sys
import zlib
from array import array
from dataclasses import dataclass


class GeoTiffError(ValueError):
    """The bytes are not a GeoTIFF this reader supports. Messages never contain URLs."""


class HeaderTruncated(GeoTiffError):
    """The header references bytes beyond the buffer; ``required`` is the size needed."""

    def __init__(self, required: int):
        super().__init__(f'TIFF header needs {required} bytes')
        self.required = required


# TIFF tags used here
_WIDTH, _HEIGHT, _BITS, _COMPRESSION, _SAMPLES, _PLANAR, _PREDICTOR = 256, 257, 258, 259, 277, 284, 317
_TILE_W, _TILE_H, _TILE_OFFSETS, _TILE_COUNTS, _SAMPLE_FORMAT = 322, 323, 324, 325, 339
_STRIP_OFFSETS = 273
_PIXEL_SCALE, _TIEPOINT, _GEOKEYS, _NODATA = 33550, 33922, 34735, 42113
_PROJECTED_CS_KEY, _RASTER_TYPE_KEY, _MODEL_TYPE_KEY = 3072, 1025, 1024

_TYPE_FORMAT = {1: 'B', 2: 's', 3: 'H', 4: 'I', 6: 'b', 7: 'B', 8: 'h', 9: 'i', 11: 'f', 12: 'd', 16: 'Q', 17: 'q'}
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 6: 1, 7: 1, 8: 2, 9: 4, 11: 4, 12: 8, 16: 8, 17: 8}
_COMPRESSION_NONE, _COMPRESSION_DEFLATE, _COMPRESSION_DEFLATE_OLD = 1, 8, 32946
_ARRAY_CODES = {(8, 1): 'B', (8, 2): 'b', (16, 1): 'H', (16, 2): 'h'}

MAX_HEADER_BYTES = 1 << 20  # a header larger than 1 MiB is not an HLS COG


@dataclass(frozen=True)
class TiffLayout:
    width: int
    height: int
    tile_width: int
    tile_height: int
    bits_per_sample: int
    sample_format: int          # 1 unsigned integer, 2 signed integer
    compression: int
    predictor: int
    tile_offsets: tuple[int, ...]
    tile_byte_counts: tuple[int, ...]
    pixel_size_x: float
    pixel_size_y: float
    origin_x: float             # map coordinate of the upper-left corner of pixel (0, 0)
    origin_y: float
    epsg: int
    nodata: float | None
    little_endian: bool

    @property
    def tiles_across(self) -> int:
        return math.ceil(self.width / self.tile_width)

    @property
    def tiles_down(self) -> int:
        return math.ceil(self.height / self.tile_height)

    def tile_index(self, col: int, row: int) -> int:
        return (row // self.tile_height) * self.tiles_across + col // self.tile_width

    def pixel_of(self, x: float, y: float) -> tuple[int, int]:
        """(col, row) of the pixel containing map coordinate (x, y); may fall outside the raster."""
        return (math.floor((x - self.origin_x) / self.pixel_size_x),
                math.floor((self.origin_y - y) / self.pixel_size_y))

    def pixel_center(self, col: int, row: int) -> tuple[float, float]:
        return (self.origin_x + (col + 0.5) * self.pixel_size_x, self.origin_y - (row + 0.5) * self.pixel_size_y)


def _read_tags(buf: bytes, bo: str) -> dict[int, tuple]:
    if len(buf) < 8:
        raise HeaderTruncated(8)
    magic = struct.unpack(bo + 'H', buf[2:4])[0]
    if magic == 43:
        raise GeoTiffError('BigTIFF is not supported')
    if magic != 42:
        raise GeoTiffError('not a TIFF file')
    ifd = struct.unpack(bo + 'I', buf[4:8])[0]
    if ifd + 2 > len(buf):
        raise HeaderTruncated(ifd + 2)
    count = struct.unpack(bo + 'H', buf[ifd:ifd + 2])[0]
    end = ifd + 2 + count * 12
    if end > len(buf):
        raise HeaderTruncated(end)
    tags: dict[int, tuple] = {}
    for i in range(count):
        entry = buf[ifd + 2 + i * 12: ifd + 14 + i * 12]
        tag, typ, n = struct.unpack(bo + 'HHI', entry[:8])
        if typ not in _TYPE_FORMAT:
            continue  # rational and other types are not needed here
        size = _TYPE_SIZE[typ] * n
        if size <= 4:
            raw = entry[8:8 + size]
        else:
            offset = struct.unpack(bo + 'I', entry[8:12])[0]
            if offset + size > len(buf):
                raise HeaderTruncated(offset + size)
            raw = buf[offset:offset + size]
        if typ == 2:
            tags[tag] = (raw.rstrip(b'\x00').decode('latin-1'),)
        else:
            tags[tag] = struct.unpack(bo + _TYPE_FORMAT[typ] * n, raw)
    return tags


def _one(tags: dict[int, tuple], tag: int, default: int | None = None) -> int:
    value = tags.get(tag)
    if value is None:
        if default is None:
            raise GeoTiffError(f'required TIFF tag {tag} missing')
        return default
    return int(value[0])


def _epsg(geokeys: tuple) -> int:
    if len(geokeys) < 4:
        raise GeoTiffError('GeoKey directory is empty')
    keys = {}
    for i in range(geokeys[3]):
        key_id, location, _count, value = geokeys[4 + i * 4: 8 + i * 4]
        if location == 0:
            keys[key_id] = value
    if keys.get(_MODEL_TYPE_KEY) != 1:
        raise GeoTiffError('raster is not in a projected coordinate system')
    if keys.get(_RASTER_TYPE_KEY, 1) != 1:
        raise GeoTiffError('only PixelIsArea rasters are supported')
    epsg = keys.get(_PROJECTED_CS_KEY)
    if not isinstance(epsg, int) or not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
        raise GeoTiffError('only WGS 84 / UTM rasters are supported')
    return epsg


def parse_header(buf: bytes) -> TiffLayout:
    """Parse the first IFD. Raises HeaderTruncated when ``buf`` is too short, GeoTiffError otherwise."""
    if buf[:2] == b'II':
        bo, little = '<', True
    elif buf[:2] == b'MM':
        bo, little = '>', False
    else:
        raise GeoTiffError('not a TIFF file')
    tags = _read_tags(buf, bo)
    if _STRIP_OFFSETS in tags or _TILE_OFFSETS not in tags:
        raise GeoTiffError('only tiled TIFFs are supported')
    if _one(tags, _SAMPLES, 1) != 1 or _one(tags, _PLANAR, 1) != 1:
        raise GeoTiffError('only single-band rasters are supported')
    bits, fmt = _one(tags, _BITS), _one(tags, _SAMPLE_FORMAT, 1)
    if (bits, fmt) not in _ARRAY_CODES:
        raise GeoTiffError('unsupported sample type')
    compression = _one(tags, _COMPRESSION, 1)
    if compression not in (_COMPRESSION_NONE, _COMPRESSION_DEFLATE, _COMPRESSION_DEFLATE_OLD):
        raise GeoTiffError('unsupported compression')
    predictor = _one(tags, _PREDICTOR, 1)
    if predictor not in (1, 2):
        raise GeoTiffError('unsupported predictor')
    offsets, counts = tags[_TILE_OFFSETS], tags.get(_TILE_COUNTS)
    width, height = _one(tags, _WIDTH), _one(tags, _HEIGHT)
    tile_w, tile_h = _one(tags, _TILE_W), _one(tags, _TILE_H)
    if min(width, height, tile_w, tile_h) <= 0:
        raise GeoTiffError('invalid raster size')
    expected_tiles = math.ceil(width / tile_w) * math.ceil(height / tile_h)
    if counts is None or len(offsets) != expected_tiles or len(counts) != expected_tiles:
        raise GeoTiffError('tile index does not match the raster size')
    scale, tie = tags.get(_PIXEL_SCALE), tags.get(_TIEPOINT)
    if not scale or not tie or len(scale) < 2 or len(tie) < 6:
        raise GeoTiffError('georeferencing tags missing')
    if tie[0] != 0 or tie[1] != 0 or not (scale[0] > 0 and scale[1] > 0):
        raise GeoTiffError('unsupported georeferencing')
    epsg = _epsg(tags[_GEOKEYS]) if _GEOKEYS in tags else None
    if epsg is None:
        raise GeoTiffError('GeoKey directory missing')
    nodata = None
    if _NODATA in tags:
        try:
            nodata = float(tags[_NODATA][0].strip())
        except ValueError as e:
            raise GeoTiffError('nodata value is not numeric') from e
    return TiffLayout(width=width, height=height, tile_width=tile_w, tile_height=tile_h, bits_per_sample=bits,
                      sample_format=fmt, compression=compression, predictor=predictor,
                      tile_offsets=tuple(offsets), tile_byte_counts=tuple(counts),
                      pixel_size_x=float(scale[0]), pixel_size_y=float(scale[1]),
                      origin_x=float(tie[3]), origin_y=float(tie[4]), epsg=epsg, nodata=nodata, little_endian=little)


def decode_tile(raw: bytes, layout: TiffLayout) -> array:
    """Decode one tile into a flat row-major array of tile_width × tile_height samples."""
    if layout.compression != _COMPRESSION_NONE:
        try:
            raw = zlib.decompress(raw)
        except zlib.error as e:
            raise GeoTiffError('tile is not valid Deflate data') from e
    code = _ARRAY_CODES[(layout.bits_per_sample, layout.sample_format)]
    expected = layout.tile_width * layout.tile_height * layout.bits_per_sample // 8
    if len(raw) != expected:
        raise GeoTiffError('decoded tile has an unexpected size')
    values = array(code)
    values.frombytes(raw)
    if layout.bits_per_sample > 8 and layout.little_endian != (sys.byteorder == 'little'):
        values.byteswap()
    if layout.predictor == 2:
        values = _undo_horizontal_differencing(values, layout)
    return values


def _undo_horizontal_differencing(values: array, layout: TiffLayout) -> array:
    bits = layout.bits_per_sample
    mask, signed = (1 << bits) - 1, layout.sample_format == 2
    half = 1 << (bits - 1)
    out = array(values.typecode, values)
    w = layout.tile_width
    for start in range(0, len(out), w):
        acc = 0
        for i in range(start, start + w):
            acc = (acc + values[i]) & mask
            out[i] = acc - (1 << bits) if signed and acc >= half else acc
    return out


# --------------------------------------------------------------------------- WGS 84 → UTM

_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996


def utm_zone_of(epsg: int) -> tuple[int, bool]:
    """(zone, northern hemisphere) for EPSG 326zz / 327zz."""
    if 32601 <= epsg <= 32660:
        return epsg - 32600, True
    if 32701 <= epsg <= 32760:
        return epsg - 32700, False
    raise GeoTiffError('not a WGS 84 / UTM EPSG code')


def latlon_to_utm(latitude: float, longitude: float, epsg: int) -> tuple[float, float]:
    """Project WGS 84 latitude/longitude to (easting, northing) in the given UTM zone.

    Krüger series to third order in n (sub-millimetre within a zone); the zone is the raster's,
    which may differ from the point's natural zone near zone edges, as UTM allows."""
    zone, north = utm_zone_of(epsg)
    n = _F / (2 - _F)
    big_a = _A / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    alpha = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    phi = math.radians(latitude)
    lam = math.radians(longitude - (zone * 6 - 183))
    lam = (lam + math.pi) % (2 * math.pi) - math.pi
    c = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    easting = eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(alpha, 1))
    northing = xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(alpha, 1))
    return 500_000.0 + _K0 * big_a * easting, (0.0 if north else 10_000_000.0) + _K0 * big_a * northing
