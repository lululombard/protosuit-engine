"""
Configuration loader for protosuit engine
Provides centralized config parsing for both engine and web interface
"""

import yaml
import os
from typing import Dict, List, Optional, Any
from .typed_config import *


class ConfigLoader:
    """Load and parse config.yaml with validation"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize config loader

        Args:
            config_path: Path to config.yaml (relative to project root or absolute)
        """
        # Handle both relative and absolute paths
        if not os.path.isabs(config_path):
            config_path = os.path.abspath(config_path)

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config from {self.config_path}: {e}")
            return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Return minimal default config if file doesn't exist"""
        return {
            "default_animation": "stars",
            "animations": {},
            "transitions": {"enabled": True, "duration": 0.75},
        }

    def _parse_typed_config(self, config_dict: Dict[str, Any], config_class) -> Any:
        """Parse config dictionary into typed config class"""
        if not config_dict:
            return config_class()

        # Filter out None values and convert to the expected type
        filtered_dict = {k: v for k, v in config_dict.items() if v is not None}
        return config_class(**filtered_dict)

    def get_animation(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get animation configuration by name

        Args:
            name: Animation name

        Returns:
            Animation config dict or None if not found
        """
        return self.config.get("animations", {}).get(name)

    def get_base_animations(self) -> List[Dict[str, Any]]:
        """
        Get all base (persistent) animations

        Returns:
            List of base animation configs with 'id' field added
        """
        animations = []
        for key, value in self.config.get("animations", {}).items():
            if value.get("type", "base") == "base":  # Default to base if not specified
                anim = value.copy()
                anim["id"] = key
                animations.append(anim)
        return animations

    def get_overlay_animations(self) -> List[Dict[str, Any]]:
        """
        Get all overlay (temporary) animations

        Returns:
            List of overlay animation configs with 'id' field added
        """
        animations = []
        for key, value in self.config.get("animations", {}).items():
            if value.get("type") == "overlay":
                anim = value.copy()
                anim["id"] = key
                animations.append(anim)
        return animations

    def get_default_animation(self) -> str:
        """
        Get default animation name

        Returns:
            Default animation name (defaults to 'stars')
        """
        return self.config.get("default_animation", "stars")

    def get_uniforms(self, animation_name: str) -> Dict[str, Any]:
        """
        Get uniforms for an animation

        Args:
            animation_name: Name of animation

        Returns:
            Uniforms dict or empty dict if not found
        """
        anim = self.get_animation(animation_name)
        if anim:
            return anim.get("uniforms", {})
        return {}

    def get_transition_config(self) -> TransitionConfig:
        """Get transition configuration"""
        config_dict = self.config.get("transitions", {})
        return self._parse_typed_config(config_dict, TransitionConfig)

    def get_mqtt_config(self) -> MQTTConfig:
        """Get MQTT configuration"""
        config_dict = self.config.get("mqtt", {})
        return self._parse_typed_config(config_dict, MQTTConfig)

    def get_web_config(self) -> WebConfig:
        """Get web interface configuration"""
        config_dict = self.config.get("web", {})
        return self._parse_typed_config(config_dict, WebConfig)

    def get_system_config(self) -> SystemConfig:
        """Get system configuration"""
        config_dict = self.config.get("system", {})
        return self._parse_typed_config(config_dict, SystemConfig)

    def get_display_config(self) -> DisplayConfig:
        """
        Get display configuration

        Returns:
            DisplayConfig object with width, height, positions
        """
        config_dict = self.config.get("display", {})
        return self._parse_typed_config(config_dict, DisplayConfig)

    def get_monitoring_config(self) -> MonitoringConfig:
        """Get monitoring configuration"""
        config_dict = self.config.get("monitoring", {})
        return self._parse_typed_config(config_dict, MonitoringConfig)

    def get_networking_config(self) -> NetworkingConfig:
        """Get networking bridge configuration"""
        config_dict = self.config.get("networkingbridge", {})
        return self._parse_typed_config(config_dict, NetworkingConfig)

    def get_esp32_config(self) -> ESP32Config:
        """Get ESP32 bridge configuration"""
        config_dict = self.config.get("esp32", {})
        return self._parse_typed_config(config_dict, ESP32Config)

    def validate(self) -> bool:
        """
        Perform basic validation on config

        Returns:
            True if config is valid, False otherwise
        """
        try:
            # Check that config is a dict
            if not isinstance(self.config, dict):
                print("Config must be a dictionary")
                return False

            # Check that animations exist
            if "animations" not in self.config:
                print("Config missing 'animations' section")
                return False

            # Check that default animation exists
            default = self.get_default_animation()
            if default not in self.config.get("animations", {}):
                print(f"Default animation '{default}' not found in animations")
                return False

            # Validate each animation has required fields
            for name, anim in self.config.get("animations", {}).items():
                anim_type = anim.get("type", "base")

                if anim_type == "base":
                    # Base animations need shaders
                    if "left_shader" not in anim or "right_shader" not in anim:
                        print(f"Base animation '{name}' missing shader fields")
                        return False

            return True
        except Exception as e:
            print(f"Validation error: {e}")
            return False

    def reload(self):
        """Reload config from file"""
        self.config = self._load_config()
