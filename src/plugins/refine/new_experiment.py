import os
import numpy as np
from nexusformat.nexus import *
from nexpy.gui.datadialogs import BaseDialog, GridParameters
from nexpy.gui.mainwindow import report_error


def show_dialog():
    dialog = ExperimentDialog()
    dialog.show()


class ExperimentDialog(BaseDialog):

    def __init__(self, parent=None):
        super(ExperimentDialog, self).__init__(parent)

        self.experiment_file = NXroot()
        self.experiment_file['entry'] = NXentry()

        self.detectors = {}
        self.entries = {}

        self.setup_instrument()

        self.set_layout(self.directorybox('Choose Home Directory'), 
                        self.instrument.grid(header=False))
        self.set_title('New Experiment')

    def setup_instrument(self):
        entry = self.experiment_file['entry']
        entry.instrument = NXinstrument()
        entry.instrument.monochromator = NXmonochromator()
        entry.instrument.detector = NXdetector()
        entry['instrument/monochromator/wavelength'] = NXfield(0.5, dtype=np.float32)
        entry['instrument/monochromator/wavelength'].attrs['units'] = 'Angstroms'
        entry['instrument/detector/distance'] = NXfield(100.0, dtype=np.float32)
        entry['instrument/detector/distance'].attrs['units'] = 'mm'
        entry['instrument/detector/pixel_size'] = NXfield(0.172, dtype=np.float32)
        entry['instrument/detector/pixel_size'].attrs['units'] = 'mm'
        self.instrument = GridParameters()
        self.instrument.add('wavelength', entry['instrument/monochromator/wavelength'], 'Wavelength (Ang)')
        self.instrument.add('distance', entry['instrument/detector/distance'], 'Detector Distance (mm)')
        self.instrument.add('pixel', entry['instrument/detector/pixel_size'], 'Pixel Size (mm)')
        self.instrument.add('positions', [0,1,2,3,4], 'Number of Detector Positions', slot=self.set_entries)
        self.instrument['positions'].value = '0'

    def setup_entry(self, position):
        entry = self.experiment_file['f%s' % position] = NXentry()
        entry.instrument = NXinstrument()
        entry.instrument.detector = NXdetector()
        entry.instrument.monochromator = NXmonochromator()
        entry['instrument/detector/beam_center_x'] = NXfield(1024.0, dtype=np.float32)
        entry['instrument/detector/beam_center_y'] = NXfield(1024.0, dtype=np.float32)
        self.detectors[position] = GridParameters()
        self.detectors[position].add('xc', entry['instrument/detector/beam_center_x'], 'Beam Center - x')
        self.detectors[position].add('yc', entry['instrument/detector/beam_center_y'], 'Beam Center - y')

    @property
    def positions(self):
        return int(self.instrument['positions'].value)
 
    def set_entries(self):
        for position in range(1,self.positions+1):
            self.setup_entry(position)
            self.layout.addLayout(self.detectors[position].grid(header=False, title='Position %s'%position))
        self.layout.addWidget(self.close_buttons(save=True))

    def get_parameters(self):
        entry = self.experiment_file['entry']
        entry['instrument/monochromator/wavelength'] = self.instrument['wavelength'].value
        entry['instrument/detector/distance'] = self.instrument['distance'].value
        entry['instrument/detector/pixel_size'] = self.instrument['pixel'].value
        for position in range(1, self.positions+1):
            entry = self.experiment_file['f%s' % position]
            entry['instrument/monochromator/wavelength'] = self.instrument['wavelength'].value
            entry['instrument/detector/distance'] = self.instrument['distance'].value
            entry['instrument/detector/pixel_size'] = self.instrument['pixel'].value
            entry['instrument/detector/beam_center_x'] = self.detectors[position]['xc'].value
            entry['instrument/detector/beam_center_y'] = self.detectors[position]['yc'].value
            entry.makelink(self.experiment_file['entry/sample'])

    def accept(self):
        home_directory = self.get_directory()
        self.get_parameters()
        self.experiment_file.save(os.path.join(home_directory, experiment+'.nxs'))
        self.treeview.tree.load(self.experiment_file.nxfilename, 'rw')
        super(ExperimentDialog, self).accept()