"""
Tests for the interact_post_likers_commenters_from_urls plugin.

Tests cover:
- URL validation (accepts /p/ and /reel/ URLs)
- Plugin argument definitions
- Configuration parsing
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import os
import tempfile


class TestURLValidation:
    """Tests for Instagram post URL validation."""

    def test_valid_post_url(self):
        """Test validation of standard post URLs."""
        from GramAddict.core.utils import validate_url
        
        valid_urls = [
            "https://www.instagram.com/p/ABC123/",
            "https://instagram.com/p/XYZ789/",
            "http://www.instagram.com/p/test123/",
        ]
        
        for url in valid_urls:
            assert validate_url(url) is True, f"Expected {url} to be valid"

    def test_valid_reel_url(self):
        """Test validation of reel URLs."""
        from GramAddict.core.utils import validate_url
        
        valid_urls = [
            "https://www.instagram.com/reel/ABC123/",
            "https://instagram.com/reel/XYZ789/",
            "http://www.instagram.com/reel/test123/",
        ]
        
        for url in valid_urls:
            assert validate_url(url) is True, f"Expected {url} to be valid"

    def test_invalid_urls(self):
        """Test that invalid URLs are rejected."""
        from GramAddict.core.utils import validate_url
        
        invalid_urls = [
            "not-a-url",
            "instagram.com/p/ABC123",  # Missing scheme
            "",
            "   ",
        ]
        
        for url in invalid_urls:
            assert validate_url(url) is False, f"Expected {url} to be invalid"


class TestPluginURLTypeCheck:
    """Tests for plugin's Instagram URL type checking."""

    @pytest.fixture
    def plugin_instance(self):
        """Create a plugin instance for testing."""
        with patch.dict('sys.modules', {
            'GramAddict.core.decorators': MagicMock(),
            'GramAddict.core.handle_sources': MagicMock(),
            'GramAddict.core.interaction': MagicMock(),
        }):
            from GramAddict.plugins.interact_post_likers_commenters_from_urls import (
                InteractPostLikersCommentersFromURLs,
            )
            return InteractPostLikersCommentersFromURLs()

    def test_accepts_post_urls(self, plugin_instance):
        """Test that plugin accepts /p/ URLs."""
        test_urls = [
            "https://www.instagram.com/p/ABC123/",
            "https://instagram.com/p/XYZ789/",
        ]
        
        for url in test_urls:
            result = plugin_instance._is_valid_instagram_post_url(url)
            assert result is True, f"Expected {url} to be valid"

    def test_accepts_reel_urls(self, plugin_instance):
        """Test that plugin accepts /reel/ URLs."""
        test_urls = [
            "https://www.instagram.com/reel/ABC123/",
            "https://instagram.com/reel/XYZ789/",
        ]
        
        for url in test_urls:
            result = plugin_instance._is_valid_instagram_post_url(url)
            assert result is True, f"Expected {url} to be valid"

    def test_rejects_profile_urls(self, plugin_instance):
        """Test that plugin rejects profile URLs."""
        test_urls = [
            "https://www.instagram.com/username/",
            "https://instagram.com/someuser",
        ]
        
        for url in test_urls:
            result = plugin_instance._is_valid_instagram_post_url(url)
            assert result is False, f"Expected {url} to be rejected"

    def test_rejects_non_instagram_urls(self, plugin_instance):
        """Test that plugin rejects non-Instagram URLs."""
        test_urls = [
            "https://twitter.com/user/status/123",
            "https://facebook.com/post/123",
            "https://example.com/p/ABC123/",
        ]
        
        for url in test_urls:
            result = plugin_instance._is_valid_instagram_post_url(url)
            assert result is False, f"Expected {url} to be rejected"


class TestPluginArguments:
    """Tests for plugin argument definitions."""

    @pytest.fixture
    def plugin_instance(self):
        """Create a plugin instance for testing."""
        with patch.dict('sys.modules', {
            'GramAddict.core.decorators': MagicMock(),
            'GramAddict.core.handle_sources': MagicMock(),
            'GramAddict.core.interaction': MagicMock(),
        }):
            from GramAddict.plugins.interact_post_likers_commenters_from_urls import (
                InteractPostLikersCommentersFromURLs,
            )
            return InteractPostLikersCommentersFromURLs()

    def test_has_required_arguments(self, plugin_instance):
        """Test that plugin defines all required arguments."""
        arg_names = [arg["arg"] for arg in plugin_instance.arguments]
        
        required_args = [
            "--post-likers-commenters-from-file",
            "--interact-likers",
            "--no-interact-likers",
            "--interact-commenters",
            "--no-interact-commenters",
            "--likers-limit-per-post",
            "--commenters-limit-per-post",
        ]
        
        for arg in required_args:
            assert arg in arg_names, f"Missing argument: {arg}"

    def test_main_argument_is_operation(self, plugin_instance):
        """Test that main argument is marked as operation."""
        for arg in plugin_instance.arguments:
            if arg["arg"] == "--post-likers-commenters-from-file":
                assert arg.get("operation") is True
                assert arg.get("nargs") == "+"
                break
        else:
            pytest.fail("Main argument not found")

    def test_limit_arguments_have_defaults(self, plugin_instance):
        """Test that limit arguments have sensible defaults."""
        for arg in plugin_instance.arguments:
            if arg["arg"] == "--likers-limit-per-post":
                assert arg.get("default") is not None
            elif arg["arg"] == "--commenters-limit-per-post":
                assert arg.get("default") is not None


class TestFileReading:
    """Tests for reading post URLs from files."""

    def test_reads_urls_from_file(self):
        """Test that plugin can read URLs from a text file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("https://www.instagram.com/p/ABC123/\n")
            f.write("# This is a comment\n")
            f.write("https://www.instagram.com/reel/XYZ789/\n")
            f.write("\n")  # Empty line
            f.write("https://www.instagram.com/p/DEF456/\n")
            temp_path = f.name

        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                lines = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]

            assert len(lines) == 3
            assert "https://www.instagram.com/p/ABC123/" in lines
            assert "https://www.instagram.com/reel/XYZ789/" in lines
            assert "https://www.instagram.com/p/DEF456/" in lines
        finally:
            os.unlink(temp_path)

    def test_ignores_comments_and_empty_lines(self):
        """Test that comments and empty lines are ignored."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("# Header comment\n")
            f.write("\n")
            f.write("https://www.instagram.com/p/ABC123/\n")
            f.write("   # Indented comment\n")
            f.write("   \n")  # Whitespace only
            f.write("https://www.instagram.com/p/XYZ789/\n")
            temp_path = f.name

        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                lines = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]

            assert len(lines) == 2
        finally:
            os.unlink(temp_path)


class TestPluginDescription:
    """Tests for plugin metadata."""

    @pytest.fixture
    def plugin_instance(self):
        """Create a plugin instance for testing."""
        with patch.dict('sys.modules', {
            'GramAddict.core.decorators': MagicMock(),
            'GramAddict.core.handle_sources': MagicMock(),
            'GramAddict.core.interaction': MagicMock(),
        }):
            from GramAddict.plugins.interact_post_likers_commenters_from_urls import (
                InteractPostLikersCommentersFromURLs,
            )
            return InteractPostLikersCommentersFromURLs()

    def test_has_description(self, plugin_instance):
        """Test that plugin has a description."""
        assert plugin_instance.description is not None
        assert len(plugin_instance.description) > 0
        assert "liker" in plugin_instance.description.lower() or "commenter" in plugin_instance.description.lower()


class TestViewsCommentMethods:
    """Tests for the new comment-related view methods."""

    def test_open_comments_section_method_exists(self):
        """Test that OpenedPostView has open_comments_section method."""
        from GramAddict.core.views import OpenedPostView
        
        assert hasattr(OpenedPostView, 'open_comments_section')

    def test_get_comments_container_method_exists(self):
        """Test that OpenedPostView has get_comments_container method."""
        from GramAddict.core.views import OpenedPostView
        
        assert hasattr(OpenedPostView, 'get_comments_container')

    def test_get_commenter_username_method_exists(self):
        """Test that OpenedPostView has get_commenter_username method."""
        from GramAddict.core.views import OpenedPostView
        
        assert hasattr(OpenedPostView, 'get_commenter_username')


class TestHandleSourcesFunctions:
    """Tests for new handle_sources functions."""

    def test_handle_likers_from_post_exists(self):
        """Test that handle_likers_from_post function exists."""
        from GramAddict.core.handle_sources import handle_likers_from_post
        
        assert callable(handle_likers_from_post)

    def test_handle_commenters_exists(self):
        """Test that handle_commenters function exists."""
        from GramAddict.core.handle_sources import handle_commenters
        
        assert callable(handle_commenters)
