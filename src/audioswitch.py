#!/usr/bin/env python3
"""AudioSwitch — Switch macOS audio devices from your menu bar."""

import rumps
import threading
import CoreAudio
import struct
import subprocess
import os
import tempfile
from PIL import Image, ImageDraw
from Foundation import NSBlockOperation, NSOperationQueue
from CoreAudio import (
    kAudioHardwarePropertyDevices,
    kAudioHardwarePropertyDefaultOutputDevice,
    kAudioHardwarePropertyDefaultInputDevice,
    kAudioDevicePropertyDeviceName,
    kAudioDevicePropertyTransportType,
    kAudioDevicePropertyStreams,
)

NULL = None

def main_thread(fn):
    op = NSBlockOperation.alloc().init()
    op.addExecutionBlock_(fn)
    NSOperationQueue.mainQueue().addOperation_(op)


def get_output_devices():
    """Get list of output audio devices."""
    _, sz, _ = CoreAudio.AudioHardwareGetPropertyInfo(
        kAudioHardwarePropertyDevices, NULL, NULL)
    _, data = CoreAudio.AudioHardwareGetProperty(
        kAudioHardwarePropertyDevices, sz, NULL)
    
    devices = []
    for i in range(len(data) // 4):
        did = struct.unpack_from('<I', data, i*4)[0]
        
        try:
            ss, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
                did, 0, False, kAudioDevicePropertyStreams)
        except:
            ss = 0
        if ss == 0:
            continue  # not an output device
        
        # Get name
        ns, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
            did, 0, False, kAudioDevicePropertyDeviceName)
        _, nd = CoreAudio.AudioDeviceGetProperty(
            did, 0, False, kAudioDevicePropertyDeviceName, ns, NULL)
        name = nd.decode('utf-8').strip('\x00').strip()
        
        # Get transport type
        try:
            ts, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
                did, 0, False, kAudioDevicePropertyTransportType)
            _, td = CoreAudio.AudioDeviceGetProperty(
                did, 0, False, kAudioDevicePropertyTransportType, ts, NULL)
            transport = struct.unpack('<I', td)[0]
        except:
            transport = 0
        
        tnames = {0x6275696c: '🔊', 0x75736220: '🔌', 0x626c7565: '🔷', 0x68647067: '🖥️', 0x61697270: '📡'}
        icon = tnames.get(transport, '🔊')
        
        devices.append({'id': did, 'name': name, 'icon': icon})
    
    return devices


def get_input_devices():
    """Get list of input audio devices."""
    _, sz, _ = CoreAudio.AudioHardwareGetPropertyInfo(
        kAudioHardwarePropertyDevices, NULL, NULL)
    _, data = CoreAudio.AudioHardwareGetProperty(
        kAudioHardwarePropertyDevices, sz, NULL)
    
    devices = []
    for i in range(len(data) // 4):
        did = struct.unpack_from('<I', data, i*4)[0]
        
        try:
            ss, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
                did, 0, True, kAudioDevicePropertyStreams)
        except:
            ss = 0
        if ss == 0:
            continue  # not an input device
        
        ns, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
            did, 0, True, kAudioDevicePropertyDeviceName)
        _, nd = CoreAudio.AudioDeviceGetProperty(
            did, 0, True, kAudioDevicePropertyDeviceName, ns, NULL)
        name = nd.decode('utf-8').strip('\x00').strip()
        
        try:
            ts, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
                did, 0, True, kAudioDevicePropertyTransportType)
            _, td = CoreAudio.AudioDeviceGetProperty(
                did, 0, True, kAudioDevicePropertyTransportType, ts, NULL)
            transport = struct.unpack('<I', td)[0]
        except:
            transport = 0
        
        tnames = {0x6275696c: '🎤', 0x75736220: '🔌', 0x626c7565: '🔷', 0x68647067: '🖥️'}
        icon = tnames.get(transport, '🎤')
        
        devices.append({'id': did, 'name': name, 'icon': icon})
    
    return devices


def get_current_output():
    """Get current default output device ID."""
    _, sz, _ = CoreAudio.AudioHardwareGetPropertyInfo(
        kAudioHardwarePropertyDefaultOutputDevice, NULL, NULL)
    _, data = CoreAudio.AudioHardwareGetProperty(
        kAudioHardwarePropertyDefaultOutputDevice, sz, NULL)
    return struct.unpack('<I', data)[0]


def set_default_output(device_id):
    """Set the default output device."""
    data = struct.pack('<I', device_id)
    CoreAudio.AudioHardwareSetProperty(
        kAudioHardwarePropertyDefaultOutputDevice, len(data), data)


def get_device_name(device_id):
    """Get name for a device by ID."""
    ns, _, _ = CoreAudio.AudioDeviceGetPropertyInfo(
        device_id, 0, False, kAudioDevicePropertyDeviceName)
    _, nd = CoreAudio.AudioDeviceGetProperty(
        device_id, 0, False, kAudioDevicePropertyDeviceName, ns, NULL)
    return nd.decode('utf-8').strip('\x00').strip()


def create_icon():
    """Generate a simple speaker icon."""
    size = 32
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Speaker body
    draw.polygon([(8, 12), (16, 8), (16, 24), (8, 20)], fill=(100, 200, 255, 255))
    draw.rectangle([6, 14, 8, 18], fill=(100, 200, 255, 255))
    # Sound waves
    for r, a in [(4, 100), (7, 80), (10, 60)]:
        draw.arc([16+r, 12-r, 16+r*2, 20+r], 270, 90, fill=(100, 200, 255, a))
    
    path = os.path.join(tempfile.gettempdir(), "audioswitch_icon.png")
    img.save(path, "PNG")
    return path


class AudioSwitch(rumps.App):
    def __init__(self):
        icon_path = create_icon()
        super().__init__("AudioSwitch", icon=icon_path, template=False)
        self.timer = rumps.Timer(self.refresh, 5)  # refresh every 5 seconds
        self.refresh()
        self.timer.start()
    
    def refresh(self, _=None):
        """Refresh the menu with current audio devices."""
        try:
            outputs = get_output_devices()
            inputs = get_input_devices()
            current_id = get_current_output()
        except Exception as e:
            print(f"Audio refresh error: {e}")
            return
        
        curr_name = get_device_name(current_id)
        # Truncate long names for menu bar
        title = curr_name
        if len(title) > 20:
            title = title[:18] + "…"
        self.title = f"🔊 {title}"
        
        self.menu.clear()
        
        # Output devices section
        out_menu = rumps.MenuItem("🔊 输出设备 / Output", dimensions=(0, 0))
        out_menu.add(rumps.separator)
        self.menu.add(out_menu)
        
        for dev in outputs:
            is_current = dev['id'] == current_id
            label = f"{'★' if is_current else ' '} {dev['icon']} {dev['name']}"
            item = rumps.MenuItem(label, callback=lambda _, d=dev: self.switch_output(d))
            if is_current:
                item.state = True
            out_menu.add(item)
        
        # Input devices section
        if inputs:
            self.menu.add(rumps.separator)
            in_menu = rumps.MenuItem("🎤 输入设备 / Input", dimensions=(0, 0))
            in_menu.add(rumps.separator)
            self.menu.add(in_menu)
            
            for dev in inputs:
                label = f"  {dev['icon']} {dev['name']}"
                item = rumps.MenuItem(label)
                in_menu.add(item)
        
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🔄 刷新 / Refresh", callback=self.refresh))
        self.menu.add(rumps.MenuItem("❌ 退出 / Quit", callback=rumps.quit_application))
    
    def switch_output(self, device):
        """Switch to the selected output device."""
        def _do_switch():
            try:
                set_default_output(device['id'])
                main_thread(lambda: rumps.notification(
                    "AudioSwitch", f"🔊 {device['name']}",
                    "音频输出已切换 / Output switched"))
                main_thread(lambda: self.refresh())
            except Exception as e:
                main_thread(lambda: rumps.notification(
                    "AudioSwitch", "❌ 切换失败", str(e)))
        threading.Thread(target=_do_switch, daemon=True).start()


if __name__ == "__main__":
    app = AudioSwitch()
    app.run()
