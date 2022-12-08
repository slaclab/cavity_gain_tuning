from PyQt5.QtCore import pyqtSlot
from lcls_tools.superconducting.scLinac import (Cryomodule, L0B, L1B, L2B, L3B)
from pydm import Display

from gain_linac import GAIN_CRYOMODULES, GainCavity


class GainTuningGUI(Display):
    def __init__(self, parent=None, args=None):
        super().__init__(parent=parent, args=args)
        self.cryomodule: Cryomodule = None
        
        non_hl_cms = L0B + L1B + L2B + L3B
        self.ui.cm_combobox.addItems([""] + non_hl_cms)
        
        self.ui.cm_combobox.currentIndexChanged.connect(self.update_cryomodule)
        self.ui.optimize_button.clicked.connect(self.optimize)
        self.ui.cav_spinbox.valueChanged.connect(self.update_channels)
    
    @pyqtSlot(int)
    def update_cryomodule(self, idx: int):
        if idx == 0:
            self.cryomodule = None
        else:
            self.cryomodule = GAIN_CRYOMODULES[self.ui.cm_combobox.currentText()]
            self.update_channels(self.ui.cav_spinbox.value())
    
    @pyqtSlot(int)
    def update_channels(self, cav_num: int):
        cavity: GainCavity = self.cryomodule.cavities[cav_num]
        self.ui.phase_high_byte.channel = cavity.phase_high_pv_str
        self.ui.phase_high_label.channel = cavity.phase_high_pv_str
        
        self.ui.phase_low_byte.channel = cavity.phase_low_pv_str
        self.ui.phase_low_label.channel = cavity.phase_low_pv_str
        
        self.ui.amp_high_byte.channel = cavity.amp_high_pv_str
        self.ui.amp_high_label.channel = cavity.amp_high_pv_str
        
        self.ui.amp_low_byte.channel = cavity.amp_low_pv_str
        self.ui.amp_low_label.channel = cavity.amp_low_pv_str
        
        self.ui.amp_gain_p_spinbox.channel = cavity.amp_gain_p_pv_str
        self.ui.amp_gain_i_spinbox.channel = cavity.amp_gain_i_pv_str
        
        self.ui.phase_gain_p_spinbox.channel = cavity.phase_gain_p_pv_str
        self.ui.phase_gain_i_spinbox.channel = cavity.phase_gain_i_pv_str
    
    @pyqtSlot()
    def optimize(self):
        cav_num = self.ui.cav_spinbox.value()
        cavity: GainCavity = self.cryomodule.cavities[cav_num]
        
        cavity.search(sys_hbw=self.ui.search_start_spinbox.value())
    
    def ui_filename(self):
        return "gain_tuning.ui"
