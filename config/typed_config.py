"""
Typed configuration classes for protosuit engine
Provides type safety and IDE autocomplete for configuration access
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List


@dataclass
class MQTTConfig:
    """MQTT broker configuration"""

    broker: str = "localhost"
    port: int = 1883
    keepalive: int = 60


@dataclass
class MonitoringConfig:
    """Renderer monitoring configuration"""

    fps_publish_interval: float = 1.0
    fps_smoothing_frames: int = 3
    enabled: bool = True


@dataclass
class DisplayConfig:
    """Display configuration"""

    width: int = 720
    height: int = 720
    left_x: int = 0
    right_x: int = 720
    y: int = 0


@dataclass
class WebConfig:
    """Web server configuration"""

    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = True


@dataclass
class SystemConfig:
    """System configuration"""

    x_display: str = ":0"
    window_class: str = "pygame"


@dataclass
class BlurConfig:
    """Blur effect configuration for transitions"""

    enabled: bool = True
    strength: float = 8.0


@dataclass
class TransitionConfig:
    """Transition configuration"""

    enabled: bool = True
    duration: float = 0.75
    easing: str = "smoothstep"
    blur: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Parse nested blur config
        if self.blur is None:
            self.blur = BlurConfig()
        elif isinstance(self.blur, dict):
            self.blur = BlurConfig(**self.blur)


@dataclass
class UniformConfig:
    """Uniform configuration"""

    type: str = "float"
    value: Any = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    target: str = "both"
    left: Optional[Any] = None
    right: Optional[Any] = None


@dataclass
class AnimationConfig:
    """Animation configuration"""

    name: str = ""
    type: str = "base"
    shader: str = ""
    uniforms: List[UniformConfig] = None
    duration: Optional[float] = None
    render_scale: Optional[float] = None
    loop: bool = False

    def __post_init__(self):
        if self.uniforms is None:
            self.uniforms = []
