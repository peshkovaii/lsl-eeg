
import os
import sys
import site
import importlib.util

# Функция для поиска пути к плагинам Qt
def find_qt_plugins():
    """Ищет путь к плагинам Qt в установленных пакетах"""
    possible_paths = []
    
    # Путь в виртуальном окружении
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # Мы в виртуальном окружении
        venv_path = sys.prefix
        possible_paths.extend([
            os.path.join(venv_path, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins'),
            os.path.join(venv_path, 'Lib', 'site-packages', 'PyQt5', 'Qt', 'plugins'),
            os.path.join(venv_path, 'Lib', 'site-packages', 'pyqt5_plugins'),
        ])
    
    # Пути в site-packages
    for path in site.getsitepackages():
        possible_paths.extend([
            os.path.join(path, 'PyQt5', 'Qt5', 'plugins'),
            os.path.join(path, 'PyQt5', 'Qt', 'plugins'),
            os.path.join(path, 'pyqt5_plugins'),
        ])
    
    # Проверяем существование путей
    for path in possible_paths:
        platforms_dir = os.path.join(path, 'platforms')
        if os.path.exists(platforms_dir) and os.path.isdir(platforms_dir):
            print(f" Найдены Qt плагины: {path}")
            return path
    
    # Если не нашли, попробуем найти через importlib
    try:
        import PyQt5
        pyqt5_path = os.path.dirname(PyQt5.__file__)
        test_path = os.path.join(pyqt5_path, 'Qt5', 'plugins')
        if os.path.exists(os.path.join(test_path, 'platforms')):
            return test_path
    except:
        pass
    
    return None

# Устанавливаем переменные окружения
qt_plugins_path = find_qt_plugins()
if qt_plugins_path:
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugins_path
    os.environ['QT_PLUGIN_PATH'] = qt_plugins_path
    print(f"QT_PLUGIN_PATH установлен: {qt_plugins_path}")
else:
    print(" Не удалось найти Qt плагины, попробуйте запустить через run_eeg_viewer.bat")

# Теперь импортируем PyQt5
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMessageBox,
    QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox,
    QScrollArea, QGroupBox, QFileDialog, QSplitter,
    QFrame, QTabWidget, QShortcut
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QKeySequence

import pyqtgraph as pg
from pyqtgraph import GraphicsLayoutWidget

import time
import csv
import threading
import numpy as np
from datetime import datetime
from collections import deque
import random
from pylsl import StreamInfo, StreamOutlet, StreamInlet, resolve_streams


CHANNEL_NAMES = [
    "Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2",
    "F7", "F8", "T3", "T4", "T5", "T6", "Fz", "Cz", "Pz", "ECG"
]
N_CH = len(CHANNEL_NAMES)

FS = 250  
DISPLAY_SEC = 5  # Сколько секунд показывать
BUFFER_SIZE = FS * DISPLAY_SEC
GUI_FPS = 30


def ch_color(i):
    """Возвращает цвет для канала"""
    return pg.intColor(i, hues=N_CH)



class EEGSimulator:
    """Генерирует фейковый ЭЭГ сигнал и отправляет в LSL"""
    
    def __init__(self, fs=FS, channels=N_CH):
        self.fs = fs
        self.channels = channels
        self.running = False
        self.thread = None
        self.t = 0
        
        
        self.amplitude = 50
        self.alpha_freq = 10
        self.beta_freq = 20
        self.theta_freq = 6
        self.delta_freq = 2
        self.noise_level = 5
        
        
        self.info = StreamInfo(
            name='EEG_Simulator',
            type='EEG',
            channel_count=channels,
            nominal_srate=fs,
            channel_format='float32',
            source_id='sim_eeg_001'
        )
        
       
        chns = self.info.desc().append_child("channels")
        for name in CHANNEL_NAMES[:channels]:
            ch = chns.append_child("channel")
            ch.append_child_value("label", name)
            ch.append_child_value("unit", "microvolts")
            ch.append_child_value("type", "EEG")
        
        self.outlet = StreamOutlet(self.info)
        print(f"✅ Создан симулятор: {channels} каналов, {fs} Гц")
    
    def generate_sample(self):
        """Генерирует один сэмпл для всех каналов"""
        sample = []
        
        for ch in range(self.channels):
            if ch < 4:  # Лобные - больше бета
                signal = (self.amplitude * 0.3 * np.sin(2 * np.pi * self.beta_freq * self.t) +
                         self.amplitude * 0.2 * np.sin(2 * np.pi * self.alpha_freq * self.t) +
                         self.noise_level * np.random.randn())
            elif ch < 8:  # Центральные - альфа + бета
                signal = (self.amplitude * 0.4 * np.sin(2 * np.pi * self.alpha_freq * self.t) +
                         self.amplitude * 0.2 * np.sin(2 * np.pi * self.beta_freq * self.t) +
                         self.noise_level * np.random.randn())
            elif ch < 12:  # Теменные - альфа
                signal = (self.amplitude * 0.6 * np.sin(2 * np.pi * self.alpha_freq * self.t) +
                         self.amplitude * 0.1 * np.sin(2 * np.pi * self.theta_freq * self.t) +
                         self.noise_level * np.random.randn())
            else:  # Затылочные - альфа + дельта
                signal = (self.amplitude * 0.5 * np.sin(2 * np.pi * self.alpha_freq * self.t) +
                         self.amplitude * 0.3 * np.sin(2 * np.pi * self.delta_freq * self.t) +
                         self.noise_level * np.random.randn())
            
            if ch > 0 and random.random() > 0.7:
                signal += sample[-1] * 0.3
            
            sample.append(float(signal))
        
        self.t += 1/self.fs
        return sample
    
    def run(self):
        """Запускает генерацию в отдельном потоке"""
        self.running = True
        
        def generate_loop():
            print("▶️ Симулятор запущен")
            next_time = time.time()
            interval = 1/self.fs
            
            while self.running:
                sample = self.generate_sample()
                self.outlet.push_sample(sample)
                
                next_time += interval
                sleep_time = next_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            print("⏹️ Симулятор остановлен")
        
        self.thread = threading.Thread(target=generate_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)


# =========================
# ПОТОК ПОЛУЧЕНИЯ ДАННЫХ
# =========================

class DataThread(threading.Thread):
    def __init__(self, inlet, fs, disp_lock, disp_buffers):
        super().__init__(daemon=True)
        self.inlet = inlet
        self.fs = fs
        self.disp_lock = disp_lock
        self.disp_buffers = disp_buffers
        self.running = True
        
        # Для логирования
        self.log_file = None
        self.log_writer = None
        self.log_enabled = False
    
    def run(self):
        while self.running:
            try:
                samples, timestamps = self.inlet.pull_chunk(timeout=0.02, max_samples=32)
                if not samples:
                    continue
                
                # Обновляем буферы отображения
                with self.disp_lock:
                    for sample in samples:
                        for i, ch in enumerate(CHANNEL_NAMES):
                            if i < len(sample):
                                self.disp_buffers[ch].append(sample[i])
                
                # Логирование
                if self.log_enabled and self.log_writer:
                    for sample, ts in zip(samples, timestamps):
                        row = [f"{ts:.6f}"] + [f"{v:.4f}" for v in sample[:N_CH]]
                        self.log_writer.writerow(row)
                    self.log_file.flush()
                    
            except Exception as e:
                print(f"Ошибка в потоке данных: {e}")
    
    def stop(self):
        self.running = False
    
    def start_logging(self, filename):
        """Начинает запись в файл"""
        self.log_file = open(filename, "w", newline="", buffering=65536)
        self.log_writer = csv.writer(self.log_file, delimiter=' ')
        self.log_writer.writerow(["timestamp"] + CHANNEL_NAMES)
        self.log_enabled = True
        return filename
    
    def stop_logging(self):
        """Останавливает запись"""
        self.log_enabled = False
        if self.log_file:
            self.log_file.flush()
            self.log_file.close()
            self.log_file = None
            self.log_writer = None


class SpectrumWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Спектральный анализ")
        self.resize(1000, 700)
        
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        self.shortcut_close = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_close.activated.connect(self.close)
        
        layout = QVBoxLayout(self)
        
        control = QFrame()
        control.setFrameStyle(QFrame.Box)
        control_layout = QHBoxLayout(control)
        
        control_layout.addWidget(QLabel("Канал:"))
        self.channel_combo = QComboBox()
        self.channel_combo.addItems([f"{i}: {name}" for i, name in enumerate(CHANNEL_NAMES)])
        control_layout.addWidget(self.channel_combo)
        
        control_layout.addWidget(QLabel("Окно (с):"))
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.5, 5.0)
        self.window_spin.setValue(2.0)
        control_layout.addWidget(self.window_spin)
        
        control_layout.addWidget(QLabel("Шаг (с):"))
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.1, 2.0)
        self.step_spin.setValue(0.5)
        self.step_spin.setSingleStep(0.1)
        control_layout.addWidget(self.step_spin)
        
        self.update_btn = QPushButton("Обновить")
        self.update_btn.clicked.connect(self.update_spectrum)
        control_layout.addWidget(self.update_btn)
        
        
        self.close_btn = QPushButton("✕ Закрыть")
        self.close_btn.clicked.connect(self.close)
        control_layout.addWidget(self.close_btn)
        
        layout.addWidget(control)
        
     
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        
        self.spectrum_widget = pg.GraphicsLayoutWidget()
        self.spectrum_plot = self.spectrum_widget.addPlot(title="Спектр мощности")
        self.spectrum_plot.setLabel('left', 'Амплитуда')
        self.spectrum_plot.setLabel('bottom', 'Частота', units='Гц')
        self.spectrum_plot.setXRange(0, 50)
        self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen('y', width=2))
        
        bands = [(0.5, 4, '#80808080', 'Дельта'),  # серый с прозрачностью
                 (4, 8, '#00FF0080', 'Тета'),      # зеленый с прозрачностью
                 (8, 13, '#FF000080', 'Альфа'),    # красный с прозрачностью
                 (13, 30, '#FFFF0080', 'Бета')]    # желтый с прозрачностью
        
        for low, high, color, name in bands:
            band = pg.LinearRegionItem(values=(low, high),
                                       brush=pg.mkBrush(color),
                                       movable=False)
            self.spectrum_plot.addItem(band)
        
        self.tabs.addTab(self.spectrum_widget, "Спектр")
        
        
        self.spec_widget = pg.GraphicsLayoutWidget()
        self.spec_plot = self.spec_widget.addPlot(title="Спектрограмма")
        self.spec_plot.setLabel('left', 'Частота', units='Гц')
        self.spec_plot.setLabel('bottom', 'Время', units='с')
        self.spec_plot.setXRange(-DISPLAY_SEC, 0)
        self.spec_plot.setYRange(0, 30)
        
        
        self.spec_img = pg.ImageItem()
        
        colors = [
            (0, 0, 128),    # темно-синий
            (0, 0, 255),    # синий
            (0, 255, 255),  # голубой
            (255, 255, 0),  # желтый
            (255, 0, 0)     # красный
        ]
        cmap = pg.ColorMap(pos=np.linspace(0, 1, len(colors)), color=colors)
        self.spec_img.setLookupTable(cmap.getLookupTable())
        
        self.spec_plot.addItem(self.spec_img)
        
        self.tabs.addTab(self.spec_widget, "Спектрограмма")
        
       
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spectrum)
        self.timer.start(1000)
        
        
        self.last_spectrogram = None
        self.last_freqs = None
        self.last_times = None
    
    def get_channel_data(self):
        if not self.parent or not self.parent.data_thread:
            return None
        channel = self.channel_combo.currentIndex()
        ch_name = CHANNEL_NAMES[channel]
        with self.parent.disp_lock:
            if ch_name in self.parent.disp_buffers:
                return np.array(list(self.parent.disp_buffers[ch_name]))
        return None
    
    def compute_fft_spectrum(self, data):
        """Вычисление спектра через FFT"""
        data = data - np.mean(data)
        fft_vals = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), 1/FS)
        amplitudes = np.abs(fft_vals * 2 / len(data))
        return freqs, amplitudes
    
    def compute_spectrogram(self, window_sec, step_sec):
        """Вычисление спектрограммы"""
        data = self.get_channel_data()
        if data is None or len(data) < FS * window_sec:
            return None, None, None
        
        window_samples = int(window_sec * FS)
        step_samples = int(step_sec * FS)
        
        n_windows = (len(data) - window_samples) // step_samples + 1
        
        if n_windows < 1:
            return None, None, None
        
        times = []
        spectro = []
        freqs = None
        
        for i in range(n_windows):
            start = i * step_samples
            end = start + window_samples
            segment = data[start:end]
            
            current_freqs, amplitudes = self.compute_fft_spectrum(segment)
            
            if freqs is None:
                freqs = current_freqs
            
            times.append(start / FS - DISPLAY_SEC)
            spectro.append(amplitudes)
        
        times = np.array(times)
        spectrogram = np.array(spectro)
        
        return times, freqs, spectrogram
    
    def update_spectrum(self):
        """Обновление спектра и спектрограммы"""
        if not self.parent or not self.parent.data_thread:
            return
        
        window_sec = self.window_spin.value()
        step_sec = self.step_spin.value()
        
        
        current_tab = self.tabs.currentIndex()
        
        if current_tab == 0:  # Спектр
            data = self.get_channel_data()
            if data is None or len(data) < FS * window_sec:
                return
            
            #
            segment = data[-int(window_sec * FS):]
            freqs, amps = self.compute_fft_spectrum(segment)
            
            # Только до 50 Гц
            mask = freqs <= 50
            self.spectrum_curve.setData(freqs[mask], amps[mask])
            
        else:  # Спектрограмма
            times, freqs, spectrogram = self.compute_spectrogram(window_sec, step_sec)
            
            if spectrogram is not None and len(spectrogram) > 0:
                self.last_spectrogram = spectrogram
                self.last_freqs = freqs
                self.last_times = times
                
                # Только до 30 Гц
                freq_mask = freqs <= 30
                img_data = spectrogram[:, freq_mask].T
                
                # Нормализуем данные для лучшего отображения
                if img_data.max() > 0:
                    img_data = img_data / img_data.max() * 255
                
                self.spec_img.setImage(img_data)
                
                # Устанавливаем экстент
                if len(times) > 1 and len(freqs[freq_mask]) > 1:
                    self.spec_img.setRect(
                        pg.QtCore.QRectF(
                            times[0], 0,
                            times[-1] - times[0],
                            freqs[freq_mask][-1]
                        )
                    )

# =========================
# ГЛАВНОЕ ОКНО
# =========================

class EEGViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LSL EEG Viewer + Симулятор")
        self.resize(1600, 900)
        
        # Переменные
        self.simulator = None
        self.inlet = None
        self.data_thread = None
        self.streams = []
        
        self.disp_lock = threading.Lock()
        self.disp_buffers = {ch: deque(maxlen=BUFFER_SIZE) for ch in CHANNEL_NAMES}
        
        self.selected_channels = list(range(8))
        self.channel_checkboxes = []
        self.select_all_cb = None  # Для чекбокса "Выбрать все"
        self.plots = {}
        self.curves = {}
        
        self.log_filename = None
        self.spectrum_window = None
        
        self.setup_ui()
        self.setup_timers()
        self.refresh_streams()
    
    def setup_ui(self):
        """Создание интерфейса"""
        # Главный сплиттер
        splitter = QSplitter(Qt.Horizontal)
        
        # Левая панель
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Симулятор
        sim_box = QGroupBox("🎮 Симулятор ЭЭГ")
        sim_layout = QVBoxLayout(sim_box)
        
        self.start_sim_btn = QPushButton("▶️ Запустить симулятор")
        self.start_sim_btn.clicked.connect(self.start_simulator)
        sim_layout.addWidget(self.start_sim_btn)
        
        self.stop_sim_btn = QPushButton("⏹️ Остановить симулятор")
        self.stop_sim_btn.clicked.connect(self.stop_simulator)
        self.stop_sim_btn.setEnabled(False)
        sim_layout.addWidget(self.stop_sim_btn)
        
        left_layout.addWidget(sim_box)
        
        # LSL потоки
        left_layout.addWidget(QLabel("📡 LSL потоки:"))
        
        self.stream_list = QListWidget()
        self.stream_list.setMaximumHeight(100)
        left_layout.addWidget(self.stream_list)
        
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self.refresh_streams)
        btn_layout.addWidget(self.refresh_btn)
        
        self.connect_btn = QPushButton("🔌 Подключиться")
        self.connect_btn.clicked.connect(self.connect_stream)
        btn_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("❌ Отключиться")
        self.disconnect_btn.clicked.connect(self.disconnect_stream)
        self.disconnect_btn.setEnabled(False)
        btn_layout.addWidget(self.disconnect_btn)
        
        left_layout.addLayout(btn_layout)
        
        self.status_label = QLabel("⏸ Ожидание")
        left_layout.addWidget(self.status_label)
        
        # Выбор каналов
        left_layout.addWidget(QLabel("✅ Каналы:"))
        
        # Чекбокс "Выбрать все"
        self.select_all_cb = QCheckBox("🔘 Выбрать все каналы")
        self.select_all_cb.stateChanged.connect(self.toggle_all_channels)
        left_layout.addWidget(self.select_all_cb)
        
        # Область с прокруткой для чекбоксов каналов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(300)
        
        check_widget = QWidget()
        check_layout = QVBoxLayout(check_widget)
        
        for i, name in enumerate(CHANNEL_NAMES):
            cb = QCheckBox(f"{i+1:2d}. {name}")
            cb.setChecked(i < 8)
            cb.stateChanged.connect(self.update_selected_channels)
            check_layout.addWidget(cb)
            self.channel_checkboxes.append(cb)
        
        scroll.setWidget(check_widget)
        left_layout.addWidget(scroll)
        
        # Масштаб - убрали "мкВ"
        scale_box = QGroupBox("🔍 Масштаб")
        scale_layout = QVBoxLayout(scale_box)
        
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(10, 500)
        self.scale_spin.setValue(50)
        # Убрали суффикс " мкВ"
        self.scale_spin.setSuffix("")
        self.scale_spin.valueChanged.connect(self.update_scale)
        scale_layout.addWidget(self.scale_spin)
        
        scale_btn_layout = QHBoxLayout()
        self.scale_up_btn = QPushButton("+")
        self.scale_up_btn.clicked.connect(lambda: self.scale_spin.setValue(self.scale_spin.value() * 0.8))
        scale_btn_layout.addWidget(self.scale_up_btn)
        
        self.scale_down_btn = QPushButton("-")
        self.scale_down_btn.clicked.connect(lambda: self.scale_spin.setValue(self.scale_spin.value() * 1.2))
        scale_btn_layout.addWidget(self.scale_down_btn)
        
        scale_layout.addLayout(scale_btn_layout)
        left_layout.addWidget(scale_box)
        
        # Кнопки
        self.spectrum_btn = QPushButton("📊 Спектр")
        self.spectrum_btn.clicked.connect(self.show_spectrum)
        self.spectrum_btn.setEnabled(False)
        left_layout.addWidget(self.spectrum_btn)
        
        self.log_btn = QPushButton("💾 Начать запись")
        self.log_btn.clicked.connect(self.toggle_logging)
        self.log_btn.setEnabled(False)
        left_layout.addWidget(self.log_btn)
        
        left_layout.addStretch()
        
        # Правая панель - графики
        self.plot_widget = GraphicsLayoutWidget()
        
        splitter.addWidget(left)
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([300, 1300])
        
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(splitter)
    
    def setup_timers(self):
        self.draw_timer = QTimer()
        self.draw_timer.timeout.connect(self.redraw_plots)
        self.draw_timer.start(1000 // GUI_FPS)
    
    def redraw_plots(self):
        if not self.plots or not self.data_thread:
            return
        
        with self.disp_lock:
            snapshots = {ch: list(self.disp_buffers[ch]) for ch in CHANNEL_NAMES}
        
        scale = self.scale_spin.value()
        
        for ch_idx in self.selected_channels:
            ch_name = CHANNEL_NAMES[ch_idx]
            if ch_name in snapshots and ch_name in self.curves:
                data = np.array(snapshots[ch_name])
                if len(data) > 1:
                    data = data - np.mean(data)
                    data = np.clip(data, -scale, scale)
                    x = np.linspace(-len(data)/FS, 0, len(data))
                    self.curves[ch_name].setData(x, data)
    
    def start_simulator(self):
        """Запуск симулятора"""
        self.simulator = EEGSimulator()
        self.simulator.run()
        
        self.start_sim_btn.setEnabled(False)
        self.stop_sim_btn.setEnabled(True)
        
        # Автоматически обновляем список потоков
        QTimer.singleShot(1000, self.refresh_streams)
    
    def stop_simulator(self):
        """Остановка симулятора"""
        if self.simulator:
            self.simulator.stop()
            self.simulator = None
        
        self.start_sim_btn.setEnabled(True)
        self.stop_sim_btn.setEnabled(False)
        
        # Если были подключены - отключаемся
        self.disconnect_stream()
        self.refresh_streams()
    
    def refresh_streams(self):
        self.stream_list.clear()
        try:
            self.streams = resolve_streams(1)
            eeg_streams = [s for s in self.streams if s.type() == "EEG"]
            
            for s in eeg_streams:
                self.stream_list.addItem(
                    f"{s.name()} | {s.channel_count()} кан. | {int(s.nominal_srate())} Гц"
                )
            
            if not eeg_streams:
                self.stream_list.addItem("❌ Нет EEG потоков")
                
        except Exception as e:
            self.stream_list.addItem(f"❌ Ошибка: {str(e)[:30]}")
    
    def connect_stream(self):
        idx = self.stream_list.currentRow()
        if idx < 0 or idx >= len(self.streams):
            return
        
        stream = self.streams[idx]
        
        try:
            self.inlet = StreamInlet(stream)
            fs = int(stream.nominal_srate())
            
            # Очищаем буферы
            with self.disp_lock:
                for ch in CHANNEL_NAMES:
                    self.disp_buffers[ch].clear()
            
            # Запускаем поток данных
            self.data_thread = DataThread(
                inlet=self.inlet,
                fs=fs,
                disp_lock=self.disp_lock,
                disp_buffers=self.disp_buffers
            )
            self.data_thread.start()
            
            # Создаем графики
            self.setup_plots()
            
            self.status_label.setText(f"✅ Подключено: {stream.name()}")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.spectrum_btn.setEnabled(True)
            self.log_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
    
    def disconnect_stream(self):
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread = None
        
        self.inlet = None
        
        self.status_label.setText("⏸ Отключено")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.spectrum_btn.setEnabled(False)
        self.log_btn.setEnabled(False)
        
        self.plot_widget.clear()
        self.plots.clear()
        self.curves.clear()
    
    def setup_plots(self):
        self.plot_widget.clear()
        self.plots.clear()
        self.curves.clear()
        
        for i, ch_idx in enumerate(self.selected_channels):
            ch_name = CHANNEL_NAMES[ch_idx]
            
            plot = self.plot_widget.addPlot(row=i, col=0)
            plot.setLabel("left", ch_name)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.setYRange(-self.scale_spin.value(), self.scale_spin.value())
            
            if i > 0:
                plot.setXLink(self.plots[CHANNEL_NAMES[self.selected_channels[0]]])
            
            curve = plot.plot(pen=pg.mkPen(ch_color(ch_idx), width=1))
            
            self.plots[ch_name] = plot
            self.curves[ch_name] = curve
        
        if self.selected_channels:
            last = self.plots[CHANNEL_NAMES[self.selected_channels[-1]]]
            last.setLabel("bottom", "Время", units="с")
    
    def update_selected_channels(self):
        """Обновление списка выбранных каналов"""
        self.selected_channels = [
            i for i, cb in enumerate(self.channel_checkboxes) if cb.isChecked()
        ]
        
        # Обновляем состояние чекбокса "Выбрать все"
        if self.select_all_cb:
            all_checked = all(cb.isChecked() for cb in self.channel_checkboxes)
            none_checked = not any(cb.isChecked() for cb in self.channel_checkboxes)
            
            # Блокируем сигналы чтобы избежать рекурсии
            self.select_all_cb.blockSignals(True)
            if all_checked:
                self.select_all_cb.setCheckState(Qt.Checked)
            elif none_checked:
                self.select_all_cb.setCheckState(Qt.Unchecked)
            else:
                self.select_all_cb.setCheckState(Qt.PartiallyChecked)
            self.select_all_cb.blockSignals(False)
        
        if self.data_thread:
            self.setup_plots()
    
    def toggle_all_channels(self, state):
        """Выбрать или снять все каналы"""
        checked = state == Qt.Checked
        
        # Блокируем сигналы для всех чекбоксов каналов
        for cb in self.channel_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        
        # Обновляем список выбранных каналов
        self.update_selected_channels()
    
    def update_scale(self):
        scale = self.scale_spin.value()
        for plot in self.plots.values():
            plot.setYRange(-scale, scale)
    
    def show_spectrum(self):
        if not self.spectrum_window:
            self.spectrum_window = SpectrumWindow(self)
        self.spectrum_window.show()
        self.spectrum_window.raise_()
    
    def toggle_logging(self):
        if not self.data_thread:
            return
        
        if not self.data_thread.log_enabled:
            # Начать запись
            fname = f"eeg_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self.data_thread.start_logging(fname)
            self.log_btn.setText("⏹️ Остановить запись")
            self.log_btn.setStyleSheet("background-color: #ffcccc;")
            self.status_label.setText(f" Запись: {fname}")
        else:
            # Остановить запись
            self.data_thread.stop_logging()
            self.log_btn.setText(" Начать запись")
            self.log_btn.setStyleSheet("")
            self.status_label.setText(" Подключено")
    
    def closeEvent(self, event):
        if self.simulator:
            self.simulator.stop()
        if self.data_thread:
            self.data_thread.stop()
        event.accept()




if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = EEGViewer()
    viewer.show()
    sys.exit(app.exec_())