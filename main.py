import sys
import sounddevice as sd
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTabWidget, QGridLayout, QFrame,
    QStackedWidget, QCheckBox, QComboBox
)
from PyQt5.QtGui import QIcon, QFont, QPainter, QPen, QColor, QImage, QPixmap
from PyQt5.QtCore import Qt, QTimer, QDate, QSize, QPropertyAnimation, QEasingCurve, pyqtProperty, QThread, pyqtSignal
import cv2

import datetime
import pyowm
import pyaudio
import wave
import os
from pocketsphinx import LiveSpeech, get_model_path, AudioFile



# Weather API setup
api_key = '0f78f82a0d9f3b4faa3462b0187c960c'  # Your API Key here as string
owm = pyowm.OWM(api_key).weather_manager()  # Use API key to get data
weather_api = owm.weather_at_place('Cairo')  # Give where you need to see the weather
data = weather_api.weather  # Get out data in the mentioned location
ref_time = datetime.datetime.fromtimestamp(data.ref_time).strftime('%Y-%m-%d %H:%M')
Humidity = data.humidity
Temperature = data.temperature('celsius')['temp']


class RecordCommand(QWidget):
    def __init__(self, parent=None, room_widget=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Control")
        self.setStyleSheet("background-color: #1a1f25;")
        self.room_widget = room_widget  # Store the reference to the RoomWidget

        self.layout = QVBoxLayout(self)

        self.command_button = QPushButton("Start Listening", self)
        self.command_button.setStyleSheet("""
            QPushButton {
                background-color: #1a1f25;
                color: white;
                border-radius: 5px;
                border: 1px solid #444;
            }
        """)
        self.command_button.clicked.connect(self.toggle_recording)
        self.layout.addWidget(self.command_button)

        self.is_listening = False  # Keep track of listening state
        self.recording = None  # Store the recording

    def toggle_recording(self):
        try:
            # Parameters for recording
            FORMAT = pyaudio.paInt16  # Audio format (16-bit)
            CHANNELS = 1  # Mono audio
            RATE = 16000  # Sampling rate (16 kHz)
            RECORD_SECONDS = 5  # Duration of recording
            OUTPUT_FILENAME = "temp_recording.wav"  # Temporary file to save the recording
            self.command_button.setText("Start Listening")

            # Initialize PyAudio
            audio = pyaudio.PyAudio()

            # Start Recording
            stream = audio.open(format=FORMAT,
                                channels=CHANNELS,
                                rate=RATE,
                                input=True,
                                frames_per_buffer=1024)

            print("Recording...")
            frames = []

            # Record for 2 seconds
            for _ in range(0, int(RATE / 1024 * RECORD_SECONDS)):
                data = stream.read(1024)
                frames.append(data)

            print("Recording finished.")

            # Stop and close the stream
            stream.stop_stream()
            stream.close()
            audio.terminate()

            # Save the recorded audio to a file
            with wave.open(OUTPUT_FILENAME, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))

            # Use pocketsphinx to process the recorded audio
            try:
                audio_file = AudioFile(
                    audio_file=OUTPUT_FILENAME,
                    hmm=get_model_path('en-us'),
                    lm=get_model_path('en-us.lm.bin'),
                    dict=get_model_path('cmudict-en-us.dict')
                )

                recognized_text = ""
                for phrase in audio_file:
                    recognized_text += str(phrase)

                print(f"Recognized Text: {recognized_text}")

                if "turn on light" in recognized_text.lower():
                    print("Turning on the light...")
                    if self.room_widget:
                        self.room_widget.light_control.power_switch._enabled = True
                        self.room_widget.light_control.power_switch.update()
                        self.room_widget.light_control.power_switch.stateChanged.emit(True)
                elif "turn off light" in recognized_text.lower():
                    print("Turning off the light...")
                    if self.room_widget:
                        self.room_widget.light_control.power_switch._enabled = False
                        self.room_widget.light_control.power_switch.update()
                        self.room_widget.light_control.power_switch.stateChanged.emit(False)
                elif "increase temperature" in recognized_text.lower():
                    print("Increasing Temperature.....")
                    current_temp = int(self.room_widget.ac_card.temp_label.text().replace("°C", ""))
                    self.room_widget.ac_card.temp_label.setText(f"{current_temp + 1}°C")
                elif "decrease temperature" in recognized_text.lower():
                    print("Decreasing Temperature.....")
                    current_temp = int(self.room_widget.ac_card.temp_label.text().replace("°C", ""))
                    self.room_widget.ac_card.temp_label.setText(f"{current_temp - 1}°C")
                else:
                    print("Command not recognized.")
            except Exception as e:
                print(f"Error processing audio file: {e}")

        except Exception as e:
            print(f"Error during recording: {e}")

        # Use a QTimer to stop recording after the duration
        self.command_button.setText("Stop Listening")
        if os.path.exists(OUTPUT_FILENAME):
            os.remove(OUTPUT_FILENAME)

class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = True

    def run(self):
        while self.running:
            ret, img = self.camera.read()
            if ret:
                rgbImage = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgbImage.shape
                bytes_per_line = ch * w
                convertToQtFormat = QImage(rgbImage.data, w, h, bytes_per_line, QImage.Format_RGB888)
                p = convertToQtFormat.scaled(640, 480, Qt.KeepAspectRatio)
                self.change_pixmap_signal.emit(p)
            else:
                print("Error: Could not read frame from camera.")
                self.stop()  # Stop the thread if camera fails to read frame

    def stop(self):
        self.running = False
        self.wait()


class CCTV(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Home - Rooms")
        self.setGeometry(100, 100, 1024, 600)
        self.setStyleSheet("background-color: #1a1f25;")

        # Initialize camera and thread
        self.camera = None
        self.thread = None

        # Main widget container
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # Layout
        self.layout = QVBoxLayout(self.central_widget)

        # Video display
        self.video_label = QLabel(self)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.video_label)

        # Camera Button
        self.camera_button = QPushButton("Start Camera", self)
        self.camera_button.clicked.connect(self.toggle_camera)
        self.layout.addWidget(self.camera_button)

    def toggle_camera(self):
        """Start/Stop Camera on button press"""
        if self.camera is None:  # Start camera
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                print("Error: Could not open camera.")
                return
            self.thread = CameraThread(self.camera)
            self.thread.change_pixmap_signal.connect(self.update_image)
            self.thread.start()
            self.camera_button.setText("Stop Camera")
        else:  # Stop camera
            self.thread.stop()
            self.camera.release()
            self.camera = None
            self.video_label.clear()
            self.camera_button.setText("Start Camera")

    def update_image(self, image):
        """Update the video label with the received image"""
        self.video_label.setPixmap(QPixmap.fromImage(image))

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.thread.stop()
        if self.camera is not None:
            self.camera.release()
        event.accept()


class CustomSwitch(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 25)
        self._enabled = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background
        if self._enabled:
            color = QColor("#3498db")
        else:
            color = QColor("#2c3e50")

        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # Draw handle
        painter.setBrush(QColor("white"))
        if self._enabled:
            pos = self.width() - 23
        else:
            pos = 3
        painter.drawEllipse(pos, 3, 19, 19)

    stateChanged = pyqtSignal(bool)  # Define the stateChanged signal

    def mousePressEvent(self, event):
        self._enabled = not self._enabled
        self.update()
        self.stateChanged.emit(self._enabled)  # Emit the signal with the current state

    @property
    def enabled(self):
        return self._enabled


class SensorCard(QFrame):
    def __init__(self, icon, title, value, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)

        layout = QVBoxLayout(self)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(title_label)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(self.value_label)

    def update_value(self, value):
        self.value_label.setText(value)


class ACCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #2c3e50;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #34495e;
            }
        """)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("AC")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px;")
        layout.addWidget(title)

        # Power switch
        self.power_switch = CustomSwitch()
        layout.addWidget(self.power_switch, alignment=Qt.AlignCenter)

        # Temperature controls
        temp_layout = QHBoxLayout()

        minus_btn = QPushButton("-")
        minus_btn.setFixedSize(30, 30)

        self.temp_label = QLabel("24°C")
        self.temp_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(30, 30)

        temp_layout.addWidget(minus_btn)
        temp_layout.addWidget(self.temp_label)
        temp_layout.addWidget(plus_btn)

        layout.addLayout(temp_layout)


class LightControlCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
            QSlider {
                height: 20px;
            }
            QSlider::groove:horizontal {
                background: #2c3e50;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        #self.light_control = LightControlCard()  # Initialize LightControlCard

        # Title
        title = QLabel("Light")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px;")
        layout.addWidget(title)

        # Power switch
        self.power_switch = CustomSwitch()
        self.power_switch.stateChanged.connect(self.toggle_lights)
        layout.addWidget(self.power_switch, alignment=Qt.AlignCenter)

        # Brightness slider
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(80)
        layout.addWidget(self.brightness_slider)

        # Brightness value
        self.brightness_label = QLabel("80%")
        self.brightness_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.brightness_label)

        self.brightness_slider.valueChanged.connect(self.update_brightness)

    def update_brightness(self, value):
        self.brightness_label.setText(f"{value}%")

    def toggle_lights(self, is_on):
        if is_on:
            print("Lights Mode: ON")
        else:
            print("Lights Mode: OFF")


class RoomWidget(QWidget):
    def __init__(self, room_name, dashboard, parent=None):
        super().__init__(parent)
        self.room_name = room_name
        self.dashboard = dashboard  # Store the dashboard (parent) reference
        self.init_ui()
        self.record_command_window = None  # To store a reference to the RecordCommand window

    def init_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(20)

        # Add sensor cards
        self.temp_card = SensorCard("🌡", "Temperature", str(Temperature))
        self.humidity_card = SensorCard("💧", "Humidity", str(Humidity))
        self.light_sensor_card = SensorCard("☀", "Light", "500 lux")

        layout.addWidget(self.temp_card, 0, 0)
        layout.addWidget(self.humidity_card, 0, 1)
        layout.addWidget(self.light_sensor_card, 0, 2)

        # Add control cards
        self.ac_card = ACCard()
        layout.addWidget(self.ac_card, 0, 3)

        self.light_control = LightControlCard()
        layout.addWidget(self.light_control, 1, 0)

        # Add room-specific controls
        if self.room_name == "Living Room":
            self.add_living_room_controls(layout)
        elif self.room_name == "Home":
            self.add_home_controls(layout)

    def handle_manual_change(self, is_on):
        if is_on:
            if self.record_command_window is None or not self.record_command_window.isVisible():
                self.record_command_window = RecordCommand(parent=self.dashboard,
                                                           room_widget=self)  # Pass self to RecordCommand
                self.record_command_window.show()
            print("Automatic Mode: ON")
        else:
            print("Automatic Mode: OFF")

    def add_living_room_controls(self, layout):
        # Add TV control
        tv_frame = QFrame()
        tv_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)
        tv_layout = QVBoxLayout(tv_frame)

        tv_title = QLabel("📺 TV Control")
        tv_title.setAlignment(Qt.AlignCenter)
        tv_title.setStyleSheet("font-size: 16px;")
        tv_layout.addWidget(tv_title)

        self.tv_power = CustomSwitch()
        tv_layout.addWidget(self.tv_power, alignment=Qt.AlignCenter)

        self.tv_channel = QComboBox()
        self.tv_channel.addItems(["Channel 1", "Channel 2", "Channel 3", "Channel 4"])
        tv_layout.addWidget(self.tv_channel)

        layout.addWidget(tv_frame, 1, 1)

        # Add speaker control
        speaker_frame = QFrame()
        speaker_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)
        speaker_layout = QVBoxLayout(speaker_frame)

        speaker_title = QLabel("🔈 Speaker Control")
        speaker_title.setAlignment(Qt.AlignCenter)
        speaker_title.setStyleSheet("font-size: 16px;")
        speaker_layout.addWidget(speaker_title)

        self.speaker_power = CustomSwitch()
        speaker_layout.addWidget(self.speaker_power, alignment=Qt.AlignCenter)

        self.speaker_volume = QSlider(Qt.Horizontal)
        self.speaker_volume.setRange(0, 100)
        self.speaker_volume.setValue(50)
        speaker_layout.addWidget(self.speaker_volume)

        layout.addWidget(speaker_frame, 1, 2)

    def add_home_controls(self, layout):
        # Add manual mode
        manual_frame = QFrame()
        manual_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)
        manual_layout = QVBoxLayout(manual_frame)

        manual_title = QLabel("🛠 Automatic Mode")
        manual_title.setAlignment(Qt.AlignCenter)
        manual_title.setStyleSheet("font-size: 16px;")
        manual_layout.addWidget(manual_title)

        self.manual_mode = CustomSwitch()
        self.manual_mode.stateChanged.connect(self.handle_manual_change)
        manual_layout.addWidget(self.manual_mode, alignment=Qt.AlignCenter)

        layout.addWidget(manual_frame, 1, 1)

        # Add WiFi control
        wifi_frame = QFrame()
        wifi_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)
        wifi_layout = QVBoxLayout(wifi_frame)

        wifi_title = QLabel("📶 WiFi Control")
        wifi_title.setAlignment(Qt.AlignCenter)
        wifi_title.setStyleSheet("font-size: 16px;")
        wifi_layout.addWidget(wifi_title)

        self.wifi_power = CustomSwitch()
        wifi_layout.addWidget(self.wifi_power, alignment=Qt.AlignCenter)

        layout.addWidget(wifi_frame, 1, 2)

        # Add door CCTV
        cctv_frame = QFrame()
        cctv_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f25;
                border-radius: 10px;
                padding: 15px;
            }
            QLabel {
                color: white;
            }
        """)
        cctv_layout = QVBoxLayout(cctv_frame)

        cctv_title = QLabel("📹 Door CCTV")
        cctv_title.setAlignment(Qt.AlignCenter)
        cctv_title.setStyleSheet("font-size: 16px;")
        cctv_layout.addWidget(cctv_title)

        self.cctv_status = QLabel("CCTV is ON")
        self.cctv_status.setAlignment(Qt.AlignCenter)
        self.cctv_status.setStyleSheet("font-size: 9px;")
        cctv_layout.addWidget(self.cctv_status)

        self.detection_button = QPushButton("Live Feed")
        self.detection_button.setStyleSheet("""
                QPushButton {
                    background-color: #1a1f25;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 10px;
                    border: 1px solid #444;
                }
            """)
        self.detection_button.clicked.connect(self.detect_person)
        cctv_layout.addWidget(self.detection_button)

        layout.addWidget(cctv_frame, 1, 3)

    def detect_person(self):
        self.cctv_window = CCTV()
        self.cctv_window.show()

        # Connect to the 'destroyed' signal
        self.cctv_window.destroyed.connect(self.handle_cctv_window_closed)

    def handle_cctv_window_closed(self):
        # Bring the dashboard to the front
        self.dashboard.activateWindow()


class SmartHomeDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My Homie")
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121518;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: #1a1f25;
                color: white;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: #2c3e50;
            }
        """)



        self.init_ui()

    def init_ui(self):
        self.setMinimumSize(1000, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Title
        title = QLabel("My Homie")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-size: 32px; font-weight: bold; margin: 20px;")
        layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        rooms = ["Home", "Living Room", "Bedroom", "Kitchen"]
        for room in rooms:
            room_widget = RoomWidget(room, self)  # Pass 'self' (SmartHomeDashboard) as the parent
            self.tabs.addTab(room_widget, room)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    dashboard = SmartHomeDashboard()
    dashboard.show()
    sys.exit(app.exec_())