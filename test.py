import subprocess
import paho.mqtt.client as mqtt
import time
import signal
import os

class FinDisplayManager:
    def __init__(self):
        self.displays = [0, 1]  # Left fin (screen 0), Right fin (screen 1)
        self.current_processes = []
        self.current_mode = None
        self.shader_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shaders')

    def cleanup_processes(self):
        """Kill all running display processes"""
        for proc in self.current_processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                proc.kill()
        self.current_processes = []

    def cleanup_all_display_processes(self):
        """Kill any existing mpv, feh, or game processes (for boot cleanup)"""
        try:
            # Kill processes using both pkill and killall for thoroughness
            for cmd in ['mpv', 'feh', 'chocolate-doom']:
                subprocess.run(['pkill', '-9', cmd], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                subprocess.run(['killall', '-9', cmd], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.2)  # Give processes time to die
            print("Cleaned up any lingering display processes")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def show_shader(self, shader_name):
        """Display shader on both fins"""
        self.cleanup_processes()

        # Run shader on both displays
        # Screen positions: HDMI-1 at 0,0 and HDMI-2 at 720,0
        positions = ['0+0', '720+0']
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        for screen_id, position in zip(self.displays, positions):
            shader_path = os.path.join(self.shader_dir, shader_name)
            proc = subprocess.Popen([
                'mpv',
                '--loop', '--no-audio',
                '--no-border',
                f'--geometry=720x720+{position}',
                '--ontop',
                f'--glsl-shader={shader_path}',
                # Use a pattern that provides frame-based time
                'av://lavfi:testsrc=size=720x720:rate=45:duration=3600'
            ], env=env)
            self.current_processes.append(proc)

        self.current_mode = 'shader'

    def show_video(self, video_path):
        """Play video on both fins (synced)"""
        self.cleanup_processes()

        # Screen positions: HDMI-1 at 0,0 and HDMI-2 at 720,0
        positions = ['0+0', '720+0']
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        for screen_id, position in zip(self.displays, positions):
            proc = subprocess.Popen([
                'mpv',
                '--loop',
                '--no-border',
                f'--geometry=720x720+{position}',
                '--ontop',
                video_path
            ], env=env)
            self.current_processes.append(proc)

        self.current_mode = 'video'

    def show_image(self, image_path):
        """Display static image on both fins"""
        self.cleanup_processes()

        # Screen positions: HDMI-1 at 0,0 and HDMI-2 at 720,0
        positions = ['0+0', '720+0']
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        for screen_id, position in zip(self.displays, positions):
            proc = subprocess.Popen([
                'feh',
                '--geometry', f'720x720+{position}',
                '--borderless',
                image_path
            ], env=env)
            self.current_processes.append(proc)

        self.current_mode = 'image'

    def launch_doom(self):
        """Launch Doom 1v1 - controllers now active"""
        self.cleanup_processes()

        # Server on left fin (screen 0)
        server_env = os.environ.copy()
        server_env['DISPLAY'] = ':0'
        server_env['SDL_VIDEO_FULLSCREEN_HEAD'] = str(self.displays[0])
        server = subprocess.Popen([
            'chocolate-doom',
            '-width', '720', '-height', '720',
            '-server', '-deathmatch'
        ], env=server_env)
        self.current_processes.append(server)

        time.sleep(2)

        # Client on right fin (screen 1)
        client_env = os.environ.copy()
        client_env['DISPLAY'] = ':0'
        client_env['SDL_VIDEO_FULLSCREEN_HEAD'] = str(self.displays[1])
        client = subprocess.Popen([
            'chocolate-doom',
            '-width', '720', '-height', '720',
            '-connect', 'localhost'
        ], env=client_env)
        self.current_processes.append(client)

        self.current_mode = 'game'

        # Notify face that we're gaming
        self.mqtt_client.publish('protogen/face/mode', 'gaming')

    def sync_with_expression(self, expression):
        """Match fin animation to face expression"""
        expression_map = {
            'happy': 'sparkles.glsl',
            'angry': 'red_pulse.glsl',
            'sad': 'blue_rain.glsl',
            'surprised': 'explosion.glsl',
            'neutral': 'idle.glsl'
        }

        shader = expression_map.get(expression, 'idle.glsl')
        self.show_shader(shader)

    def handle_mqtt(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()

        print(f"Received: {topic} = {payload}")

        if topic == 'protogen/fins/shader':
            self.show_shader(payload)

        elif topic == 'protogen/fins/video':
            self.show_video(payload)

        elif topic == 'protogen/fins/image':
            self.show_image(payload)

        elif topic == 'protogen/fins/sync':
            self.sync_with_expression(payload)

        elif topic == 'protogen/fins/game':
            if payload == 'doom':
                self.launch_doom()
            # Add other games here

        elif topic == 'protogen/fins/mode':
            if payload == 'idle':
                self.show_shader('idle.glsl')

        elif topic == 'protogen/fins/status':
            self.mqtt_client.publish('protogen/fins/status/response', self.current_mode)

    def start(self):
        # Clean up any lingering processes from previous runs
        self.cleanup_all_display_processes()
        time.sleep(0.5)  # Brief pause to let processes die

        # Setup MQTT
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_message = self.handle_mqtt
        self.mqtt_client.connect('localhost', 1883)
        self.mqtt_client.subscribe('protogen/fins/#')

        # Start with idle
        self.show_shader('idle.glsl')

        # Run forever
        try:
            self.mqtt_client.loop_forever()
        except KeyboardInterrupt:
            self.cleanup_processes()

if __name__ == '__main__':
    manager = FinDisplayManager()
    manager.start()
