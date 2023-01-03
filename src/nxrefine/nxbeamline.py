# -----------------------------------------------------------------------------
# Copyright (c) 2015-2023, AXMAS Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING, distributed with this software.
# -----------------------------------------------------------------------------

import re
from datetime import datetime
from pathlib import Path

import fabio
import numpy as np
from nexusformat.nexus import (NeXusError, NXattenuator, NXcollection, NXdata,
                               NXentry, NXfield, NXfilter, NXgoniometer,
                               NXinstrument, NXmonitor, NXsource, NXsubentry,
                               nxopen)
from nexusformat.nexus.tree import natural_sort

from .nxutils import SpecParser

prefix_pattern = re.compile(r'^([^.]+)(?:(?<!\d)|(?=_))')
index_pattern = re.compile(r'^(.*?)([0-9]*)[.](.*)$')


def get_beamline(beamline, reduce=None):
    if beamline == 'Sector6':
        return Sector6Beamline(reduce)
    elif beamline == 'QM2':
        return QM2Beamline(reduce)


class NXBeamLine:
    """Generic class containing facility-specific information"""

    def __init__(self, reduce=None):
        self.reduce = reduce
        if self.reduce:
            self.directory = Path(self.reduce.directory)
            self.root = self.reduce.root
            self.entry = self.reduce.entry
            self.scan = self.reduce.scan
            self.sample = self.reduce.sample
            self.label = self.reduce.LabelEntry
        self.probe = 'xrays'

    def __repr__(self):
        return f"NXBeamLine('{self.beamline}')"

    def import_data(self):
        pass

    def read_logs(self):
        pass


class Sector6Beamline(NXBeamLine):

    def __init__(self, reduce=None):
        super().__init__(reduce)
        self.beamline = '6-ID-D'
        self.source = 'APS'
        self.source_name = 'Advanced Photon Source'
        self.source_type = 'Synchrotron X-Ray Source'

    def load_data(self):
        if self.reduce.raw_data_exists():
            return True
        else:
            return False

    def read_logs(self):
        """Read metadata from experimental scans."""
        head_file = self.directory / self.entry.nxname+'_head.txt'
        meta_file = self.directory / self.entry.nxname+'_meta.txt'
        if head_file.exists() and meta_file.exists():
            logs = NXcollection()
        else:
            if not head_file.exists():
                self.logger.info(
                    f"'{self.entry.nxname}_head.txt' does not exist")
            if not meta_file.exists():
                self.logger.info(
                    f"'{self.entry.nxname}_meta.txt' does not exist")
            raise NeXusError('Metadata files not available')
        with open(head_file) as f:
            lines = f.readlines()
        for line in lines:
            key, value = line.split(', ')
            value = value.strip('\n')
            try:
                value = float(value)
            except Exception:
                pass
            logs[key] = value
        meta_input = np.genfromtxt(meta_file, delimiter=',', names=True)
        for i, key in enumerate(meta_input.dtype.names):
            logs[key] = [array[i] for array in meta_input]

        with self.root.nxfile:
            if 'instrument' not in self.entry:
                self.entry['instrument'] = NXinstrument()
            if 'logs' in self.entry['instrument']:
                del self.entry['instrument/logs']
            self.entry['instrument/logs'] = logs
            frame_number = self.entry['data/frame_number']
            frames = frame_number.size
            if 'MCS1' in logs:
                if 'monitor1' in self.entry:
                    del self.entry['monitor1']
                data = logs['MCS1'][:frames]
                # Remove outliers at beginning and end of frames
                data[0] = data[1]
                data[-1] = data[-2]
                self.entry['monitor1'] = NXmonitor(NXfield(data, name='MCS1'),
                                                   frame_number)
                if 'data/frame_time' in self.entry:
                    self.entry['monitor1/frame_time'] = (
                        self.entry['data/frame_time'])
            if 'MCS2' in logs:
                if 'monitor2' in self.entry:
                    del self.entry['monitor2']
                data = logs['MCS2'][:frames]
                # Remove outliers at beginning and end of frames
                data[0] = data[1]
                data[-1] = data[-2]
                self.entry['monitor2'] = NXmonitor(NXfield(data, name='MCS2'),
                                                   frame_number)
                if 'data/frame_time' in self.entry:
                    self.entry['monitor2/frame_time'] = (
                        self.entry['data/frame_time'])
            if 'source' not in self.entry['instrument']:
                self.entry['instrument/source'] = NXsource()
            self.entry['instrument/source/name'] = self.source
            self.entry['instrument/source/type'] = self.source_type
            self.entry['instrument/source/probe'] = 'x-ray'
            if 'Storage_Ring_Current' in logs:
                self.entry['instrument/source/current'] = (
                    logs['Storage_Ring_Current'])
            if 'SCU_Current' in logs:
                self.entry['instrument/source/undulator_current'] = (
                    logs['SCU_Current'])
            if 'UndulatorA_gap' in logs:
                self.entry['instrument/source/undulator_gap'] = (
                    logs['UndulatorA_gap'])
            if 'Calculated_filter_transmission' in logs:
                if 'attenuator' not in self.entry['instrument']:
                    self.entry['instrument/attenuator'] = NXattenuator()
                self.entry['instrument/attenuator/attenuator_transmission'] = (
                    logs['Calculated_filter_transmission'])
            if 'Shutter' in logs:
                if 'filter' not in self.entry['instrument']:
                    self.entry['instrument/filter'] = NXfilter()
                transmission = NXfield(1.0 - logs['Shutter'][:frames],
                                       name='transmission')
                frames = NXfield(np.array(range(frames)), name='frame_number')
                if 'transmission' in self.entry['instrument/filter']:
                    del self.entry['instrument/filter/transmission']
                self.entry['instrument/filter/transmission'] = (
                    NXdata(transmission, frames))
                time_path = 'entry/instrument/NDAttributes/NDArrayTimeStamp'
            if time_path in self.root:
                start = datetime.fromtimestamp(f[time_path][0])
                # In EPICS, the epoch started in 1990, not 1970
                start_time = start.replace(year=start.year+20).isoformat()
                self.entry['start_time'] = start_time
                self.entry['data/frame_time'].attrs['start'] = start_time


class QM2Beamline(NXBeamLine):

    def __init__(self, reduce=None):
        super().__init__(reduce)
        self.beamline = 'QM2'
        self.source = 'CHESS'
        self.source_name = 'Cornell High-Energy Synchrotron'
        parts = self.directory.parts
        self.cycle_path = Path(parts[-6], parts[-5])
        self.raw_directory = Path('/nfs/chess/id4b/') / self.cycle_path

    def load_data(self):
        if self.reduce.raw_data_exists():
            return
        self.scan_number = self.entry['scan_number'].nxvalue
        scan_directory = f"{self.sample}_{self.scan_number:03d}"
        self.image_directory = (self.raw_directory / 'raw6M' / self.sample /
                                self.label / self.scan / scan_directory)
        self.raw_file = self.directory / self.entry.nxname+'.nxs'
        self.write_data()

    def get_prefix(self):
        prefixes = []
        for filename in self.image_directory.iterdir():
            match = prefix_pattern.match(filename.stem)
            if match and filename.suffix in ['.cbf', '.tif', '.tiff']:
                prefixes.append(match.group(1).strip('-').strip('_'))
        return max(prefixes, key=prefixes.count)

    def get_index(self, filename):
        return int(index_pattern.match(str(filename)).group(2))

    def get_files(self):
        prefix = self.get_prefix()
        return sorted(
            [str(f) for f in self.image_directory.glob(prefix+'*')],
            key=natural_sort)

    def read_image(self, filename):
        im = fabio.open(str(filename))
        return im.data

    def read_images(self, filenames, shape):
        good_files = [str(f) for f in filenames if f is not None]
        if good_files:
            v0 = self.read_image(good_files[0])
            if v0.shape != shape:
                raise NeXusError(
                    f'Image shape of {good_files[0]} not consistent')
            v = np.empty([len(filenames), v0.shape[0], v0.shape[1]],
                         dtype=np.float32)
        else:
            v = np.empty([len(filenames), shape[0], shape[1]],
                         dtype=np.float32)
        v.fill(np.nan)
        for i, filename in enumerate(filenames):
            if filename:
                v[i] = self.read_image(filename)
        return v

    def initialize_entry(self, filenames):
        z_size = len(filenames)
        v0 = self.read_image(filenames[0])
        x = NXfield(range(v0.shape[1]), dtype=np.uint16, name='x_pixel')
        y = NXfield(range(v0.shape[0]), dtype=np.uint16, name='y_pixel')
        z = NXfield(np.arange(z_size), dtype=np.uint16, name='frame_number',
                    maxshape=(5000,))
        v = NXfield(name='data', shape=(z_size, v0.shape[0], v0.shape[1]),
                    dtype=np.float32,
                    maxshape=(5000, v0.shape[0], v0.shape[1]))
        return NXentry(NXdata(v, (z, y, x)))

    def write_data(self):
        filenames = self.get_files()
        with nxopen(self.raw_file, 'w') as root:
            root['entry'] = self.initialize_entry()
            z_size = root['entry/data/data'].shape[0]
            image_shape = root['entry/data/data'].shape[1:3]
            chunk_size = root['entry/data/data'].chunks[0]
            k = 0
            for i in range(0, z_size, chunk_size):
                files = []
                for j in range(i, min(i+chunk_size, z_size)):
                    if j == self.get_index(filenames[k]):
                        print('Processing', filenames[k])
                        files.append(filenames[k])
                        k += 1
                    elif k < len(filenames):
                        files.append(None)
                    else:
                        break
                root['entry/data/data'][i:i+len(files), :, :] = (
                    self.read_images(files, image_shape))

    def read_logs(self):
        spec_file = Path('/nfs/chess/id4b') / self.cycle_path / self.sample
        if not spec_file.exists():
            self.reduce.logger.info(f"'{spec_file}' does not exist")
            raise NeXusError('SPEC file not found')
        logs = SpecParser(spec_file).read(self.scan_number).NXentry[0]
        logs.nxclass = NXsubentry

        with self.root.nxfile:
            if 'logs' in self.entry:
                del self.entry['logs']
            self.entry['logs'] = logs
            frame_number = self.entry['data/frame_number']
            frames = frame_number.size
            if 'date' in logs:
                self.entry['start_time'] = logs['data']
                self.entry['data/frame_time'].attrs['start'] = logs['data']
            if 'flyc1' in logs['data']:
                if 'monitor1' in self.entry:
                    del self.entry['monitor1']
                data = logs['data/flyc1'][:frames]
                # Remove outliers at beginning and end of frames
                data[0:2] = data[2]
                data[-2:] = data[-3]
                self.entry['monitor1'] = NXmonitor(NXfield(data, name='flyc1'),
                                                   frame_number)
                if 'data/frame_time' in self.entry:
                    self.entry['monitor1/frame_time'] = (
                        self.entry['data/frame_time'])
            if 'flyc2' in logs['data']:
                if 'monitor2' in self.entry:
                    del self.entry['monitor2']
                data = logs['data/flyc2'][:frames]
                # Remove outliers at beginning and end of frames
                data[0:2] = data[2]
                data[-2:] = data[-3]
                self.entry['monitor2'] = NXmonitor(NXfield(data, name='flyc2'),
                                                   frame_number)
                if 'data/frame_time' in self.entry:
                    self.entry['monitor2/frame_time'] = (
                        self.entry['data/frame_time'])
            if 'instrument' not in self.entry:
                self.entry['instrument'] = NXinstrument()
            if 'source' not in self.entry['instrument']:
                self.entry['instrument/source'] = NXsource()
            self.entry['instrument/source/name'] = self.source
            self.entry['instrument/source/type'] = self.source_type
            self.entry['instrument/source/probe'] = 'x-ray'
            if 'goniometer' not in self.entry['instrument']:
                self.entry['instrument/goniometer'] = NXgoniometer()
            if 'chi' in logs['positioners']:
                self.entry['instrument/goniometer/chi'] = (
                    logs['positioners/chi'] - 90.0)
            if 'th' in log['positioners']:
                self.entry['instrument/goniometer/gonpitch'] = (
                    logs['positioners/th'])
