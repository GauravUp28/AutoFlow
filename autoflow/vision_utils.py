"""
Vision utilities for multimodal LLM support in AutoFlow.
Handles image processing, optimization, and provider-specific message formatting.
"""

import base64
import os
from io import BytesIO
from typing import Optional, Tuple, List, Dict, Any

# Vision-capable model mappings
VISION_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-vision-preview", "gpt-4-turbo"],
    "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
                  "claude-3-5-sonnet", "claude-3-5-sonnet-latest", "claude-opus-4"],
    "gemini": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro-vision",
               "gemini-2.0-flash", "gemini-2.5-pro"]
}


def is_vision_enabled() -> bool:
    """Check if vision mode is enabled via environment variable."""
    return os.getenv("USE_VISION", "0").lower() in ("1", "true", "yes")


def get_vision_model(provider: str) -> Optional[str]:
    """
    Get the vision-capable model for a provider.
    Returns None if vision is disabled or no vision model available.
    """
    if not is_vision_enabled():
        return None

    # Check for explicit vision model override
    vision_model = os.getenv("VISION_MODEL")
    if vision_model:
        return vision_model

    # Use default vision-capable model for provider
    provider_lower = provider.lower()
    default_models = {
        "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    }

    model = default_models.get(provider_lower)
    if model:
        # Check if model is vision-capable
        for vision_model_name in VISION_MODELS.get(provider_lower, []):
            if vision_model_name in model.lower():
                return model

    # Return default vision model for provider if current model not vision-capable
    vision_defaults = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-latest",
        "gemini": "gemini-1.5-pro"
    }
    return vision_defaults.get(provider_lower)


def optimize_image_for_api(
    image_bytes: bytes,
    max_dimension: int = None,
    quality: int = 85,
    output_format: str = "PNG"
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize an image for API transmission - resize if needed and compress.

    Args:
        image_bytes: Raw PNG screenshot bytes
        max_dimension: Maximum width or height (default from env or 1568)
        quality: JPEG quality if converting (not used for PNG)
        output_format: Output format (PNG recommended for screenshots)

    Returns:
        Tuple of (optimized_bytes, metadata_dict)
    """
    if max_dimension is None:
        max_dimension = int(os.getenv("VISION_MAX_DIMENSION", "1568"))

    try:
        from PIL import Image

        img = Image.open(BytesIO(image_bytes))
        original_size = img.size

        # Calculate resize ratio if needed
        width, height = img.size
        resized = False
        if width > max_dimension or height > max_dimension:
            ratio = min(max_dimension / width, max_dimension / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            resized = True

        # Convert to RGB if necessary (e.g., RGBA -> RGB for JPEG)
        if output_format.upper() == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Save to bytes
        output = BytesIO()
        if output_format.upper() == "PNG":
            img.save(output, format="PNG", optimize=True)
        else:
            img.save(output, format="JPEG", quality=quality, optimize=True)

        optimized_bytes = output.getvalue()

        metadata = {
            "original_size": original_size,
            "optimized_size": img.size,
            "original_bytes": len(image_bytes),
            "optimized_bytes": len(optimized_bytes),
            "format": output_format,
            "resized": resized,
            "compression_ratio": round(len(optimized_bytes) / len(image_bytes), 2) if image_bytes else 1.0
        }

        return optimized_bytes, metadata

    except Exception as e:
        # Return original on error
        return image_bytes, {
            "error": str(e),
            "optimized": False,
            "original_bytes": len(image_bytes),
            "optimized_bytes": len(image_bytes)
        }


def encode_image_base64(image_bytes: bytes) -> str:
    """Encode image bytes to base64 string."""
    return base64.b64encode(image_bytes).decode("utf-8")


def prepare_screenshot_for_vision(
    page_or_bytes,
    max_dimension: int = None
) -> Optional[Tuple[str, bytes, Dict[str, Any]]]:
    """
    Capture or process screenshot and prepare for vision API.

    Args:
        page_or_bytes: Playwright page object or raw screenshot bytes
        max_dimension: Maximum dimension for optimization

    Returns:
        Tuple of (base64_encoded_image, optimized_bytes, metadata) or None if failed
    """
    try:
        # Get raw bytes
        if isinstance(page_or_bytes, bytes):
            raw_bytes = page_or_bytes
        else:
            # Assume it's a Playwright page
            if page_or_bytes.is_closed():
                return None
            raw_bytes = page_or_bytes.screenshot()

        # Optimize
        optimized_bytes, metadata = optimize_image_for_api(
            raw_bytes, max_dimension=max_dimension
        )

        # Encode
        b64 = encode_image_base64(optimized_bytes)
        metadata["base64_length"] = len(b64)

        return b64, optimized_bytes, metadata

    except Exception as e:
        print(f"[yellow]Failed to prepare screenshot for vision: {e}[/yellow]")
        return None


def build_openai_vision_message(
    prompt: str,
    image_base64: str,
    detail: str = "auto"
) -> List[Dict[str, Any]]:
    """
    Build OpenAI-format message with image.

    Args:
        prompt: Text prompt to send
        image_base64: Base64-encoded image
        detail: Image detail level ('auto', 'low', 'high')

    Returns:
        List of message dicts for OpenAI API
    """
    return [{
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": detail
                }
            },
            {"type": "text", "text": prompt}
        ]
    }]


def build_anthropic_vision_message(
    prompt: str,
    image_base64: str
) -> List[Dict[str, Any]]:
    """
    Build Anthropic-format message with image.

    Args:
        prompt: Text prompt to send
        image_base64: Base64-encoded image

    Returns:
        List of message dicts for Anthropic API
    """
    return [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_base64
                }
            },
            {"type": "text", "text": prompt}
        ]
    }]


def build_gemini_vision_content(prompt: str, image_bytes: bytes):
    """
    Build Gemini-format content with image.

    Args:
        prompt: Text prompt to send
        image_bytes: Raw image bytes

    Returns:
        List of content parts for Gemini API
    """
    try:
        import google.generativeai as genai
        image_part = genai.types.Part.from_data(
            data=image_bytes,
            mime_type="image/png"
        )
        return [image_part, prompt]
    except ImportError:
        # Return just prompt if genai not available
        return [prompt]


class VisionMetrics:
    """Track vision API usage metrics throughout execution."""

    def __init__(self):
        self.calls = 0
        self.successes = 0
        self.fallbacks = 0
        self.total_image_bytes = 0
        self.total_optimized_bytes = 0

    def record_call(self, success: bool, original_bytes: int = 0, optimized_bytes: int = 0):
        """Record a vision API call."""
        self.calls += 1
        self.total_image_bytes += original_bytes
        self.total_optimized_bytes += optimized_bytes
        if success:
            self.successes += 1
        else:
            self.fallbacks += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "vision_enabled": is_vision_enabled(),
            "vision_calls": self.calls,
            "vision_successes": self.successes,
            "vision_fallbacks": self.fallbacks,
            "vision_image_bytes_total": self.total_image_bytes,
            "vision_optimized_bytes_total": self.total_optimized_bytes,
            "vision_compression_savings": self.total_image_bytes - self.total_optimized_bytes
        }
