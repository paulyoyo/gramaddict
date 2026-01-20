"""
Comprehensive pytest tests for ELLA name-based targeting feature.

Tests cover:
- Name detection in usernames and biographies
- Case-insensitive matching
- Message and comment loading with ELLA-specific files
- {{nombre}} variable replacement
- Storage tracking of ELLA targets
- Edge cases and error handling
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, Mock, patch
from typing import Tuple

import pytest

# Initialize the module-level args and configs variables before tests run
import GramAddict.core.filter as filter_module
if not hasattr(filter_module, 'args'):
    filter_module.args = None
if not hasattr(filter_module, 'configs'):
    filter_module.configs = None

import GramAddict.core.interaction as interaction_module
if not hasattr(interaction_module, 'args'):
    interaction_module.args = None


def create_mock_args(ella_enabled=True, ella_name="Andrea", ella_variations=None):
    """Helper to create mock args object."""
    args = Mock()
    args.ella_targeting_enabled = ella_enabled
    args.ella_targeting_name = ella_name
    # Use None as sentinel - if explicitly passed as [], keep it empty
    if ella_variations is None:
        args.ella_targeting_variations = ["Andre", "Andreita", "Andri", "Andy"]
    else:
        args.ella_targeting_variations = ella_variations
    args.disable_filters = True  # Disable filters to simplify testing
    args.app_id = "com.instagram.android"
    return args


def create_mock_filter_with_ella(args):
    """Create a Filter instance properly mocked for ELLA testing."""
    from GramAddict.core.filter import Filter
    
    # Set module-level args
    filter_module.args = args
    
    # Create mock configs
    mock_configs = Mock()
    mock_configs.args = args
    filter_module.configs = mock_configs
    
    # Create mock storage
    mock_storage = Mock()
    mock_storage.filter_path = "/nonexistent/path"
    
    with patch("os.path.exists", return_value=False):
        return Filter(storage=mock_storage)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_args_ella_enabled():
    """Mock args object with ELLA targeting enabled."""
    return create_mock_args(ella_enabled=True, ella_name="Andrea", 
                           ella_variations=["Andre", "Andreita", "Andri", "Andy"])


@pytest.fixture
def mock_args_ella_disabled():
    """Mock args object with ELLA targeting disabled."""
    return create_mock_args(ella_enabled=False, ella_name=None, ella_variations=[])


@pytest.fixture
def mock_args_ella_no_variations():
    """Mock args object with ELLA targeting enabled but no variations."""
    return create_mock_args(ella_enabled=True, ella_name="Andrea", ella_variations=[])


@pytest.fixture
def temp_account_folder():
    """Create temporary account folder with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        account_dir = os.path.join(tmpdir, "accounts", "test_user")
        os.makedirs(account_dir)
        
        # Create pm_list.txt (default messages)
        pm_list_path = os.path.join(account_dir, "pm_list.txt")
        with open(pm_list_path, "w", encoding="utf-8") as f:
            f.write("Hello! How are you?\n")
            f.write("Nice to meet you!\n")
            f.write("Check out my profile!\n")
        
        # Create comments_list.txt (default comments)
        comments_list_path = os.path.join(account_dir, "comments_list.txt")
        with open(comments_list_path, "w", encoding="utf-8") as f:
            f.write("%PHOTO\n")
            f.write("Nice photo!\n")
            f.write("Love it!\n")
            f.write("%VIDEO\n")
            f.write("Great video!\n")
            f.write("%CAROUSEL\n")
            f.write("Amazing content!\n")
        
        # Create pm_ella.txt (ELLA-specific messages)
        pm_ella_path = os.path.join(account_dir, "pm_ella.txt")
        with open(pm_ella_path, "w", encoding="utf-8") as f:
            f.write("Hola {{nombre}}! 🎉 Este viernes la fiesta ELLA lleva tu nombre\n")
            f.write("{{nombre}}! 💃 Cada viernes ELLA tiene nombre de mujer\n")
            f.write("Hey {{nombre}}! Viste que este viernes ELLA se llama como tú?\n")
        
        # Create comments_ella.txt (ELLA-specific comments)
        comments_ella_path = os.path.join(account_dir, "comments_ella.txt")
        with open(comments_ella_path, "w", encoding="utf-8") as f:
            f.write("%PHOTO\n")
            f.write("Qué buen perfil {{nombre}}! 💜\n")
            f.write("Me gusta tu estilo {{nombre}} ✨\n")
            f.write("%VIDEO\n")
            f.write("{{nombre}} qué buen contenido! 🙌\n")
            f.write("%CAROUSEL\n")
            f.write("Me encantó todo {{nombre}}! 💜\n")
        
        yield tmpdir


@pytest.fixture
def temp_account_folder_no_ella_files():
    """Create temporary account folder without ELLA-specific files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        account_dir = os.path.join(tmpdir, "accounts", "test_user")
        os.makedirs(account_dir)
        
        # Create only default files
        pm_list_path = os.path.join(account_dir, "pm_list.txt")
        with open(pm_list_path, "w", encoding="utf-8") as f:
            f.write("Hello! How are you?\n")
            f.write("Nice to meet you!\n")
        
        comments_list_path = os.path.join(account_dir, "comments_list.txt")
        with open(comments_list_path, "w", encoding="utf-8") as f:
            f.write("%PHOTO\n")
            f.write("Nice photo!\n")
            f.write("%VIDEO\n")
            f.write("Great video!\n")
            f.write("%CAROUSEL\n")
            f.write("Amazing content!\n")
        
        yield tmpdir


@pytest.fixture
def sample_ella_messages():
    """Sample ELLA messages for testing."""
    return [
        "Hola {{nombre}}! 🎉 Este viernes la fiesta ELLA lleva tu nombre",
        "{{nombre}}! 💃 Cada viernes ELLA tiene nombre de mujer",
        "Hey {{nombre}}! Viste que este viernes ELLA se llama como tú?",
    ]


@pytest.fixture
def sample_ella_comments():
    """Sample ELLA comments organized by media type."""
    return {
        "photo": ["Qué buen perfil {{nombre}}! 💜", "Me gusta tu estilo {{nombre}} ✨"],
        "video": ["{{nombre}} qué buen contenido! 🙌"],
        "carousel": ["Me encantó todo {{nombre}}! 💜"],
    }


# =============================================================================
# Test Classes
# =============================================================================

class TestEllaNameDetection:
    """Tests for name/variation detection in username and biography."""

    # -------------------------------------------------------------------------
    # Username Detection Tests
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("username,expected_match,expected_name", [
        # Exact name matches
        ("andrea_lima", True, "Andrea"),
        ("andrea", True, "Andrea"),
        ("user_andrea", True, "Andrea"),
        
        # Variation matches
        ("andre_photo", True, "Andre"),
        ("andreita_travels", True, "Andreita"),
        ("andri_fitness", True, "Andri"),
        ("andy_music", True, "Andy"),
        
        # Partial matches (name as substring)
        ("andreina_style", True, "Andre"),  # Contains "andre"
        ("alexandrea_art", True, "Andrea"),  # Contains "andrea"
        
        # Name at different positions
        ("andrea_at_start", True, "Andrea"),
        ("middle_andrea_here", True, "Andrea"),
        ("end_with_andrea", True, "Andrea"),
        
        # No match cases
        ("john_doe", False, ""),
        ("maria_garcia", False, ""),
        ("random_user123", False, ""),
    ])
    def test_username_detection(self, mock_args_ella_enabled, username, expected_match, expected_name):
        """Test that names and variations are detected in usernames."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, matched_name = filter_instance.is_ella_target(username, "")
        
        assert is_match == expected_match
        if expected_match:
            assert matched_name.lower() in [n.lower() for n in [mock_args_ella_enabled.ella_targeting_name] + mock_args_ella_enabled.ella_targeting_variations]

    # -------------------------------------------------------------------------
    # Case Insensitivity Tests
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("username", [
        "ANDREA_lima",
        "andrea_lima",
        "AnDrEa_lima",
        "aNdReA_lima",
        "Andrea_Lima",
    ])
    def test_case_insensitive_username_detection(self, mock_args_ella_enabled, username):
        """Test that username matching is case-insensitive."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, matched_name = filter_instance.is_ella_target(username, "")
        
        assert is_match is True
        assert matched_name.lower() == "andrea"

    @pytest.mark.parametrize("biography", [
        "Hola soy ANDREA de Lima",
        "Me llamo andrea y soy fotógrafa",
        "AnDrEa | Diseñadora gráfica",
        "🎨 aNdReA artista visual",
    ])
    def test_case_insensitive_biography_detection(self, mock_args_ella_enabled, biography):
        """Test that biography matching is case-insensitive."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, matched_name = filter_instance.is_ella_target("random_user", biography)
        
        assert is_match is True

    # -------------------------------------------------------------------------
    # Biography Detection Tests
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("biography,expected_match", [
        ("Hola soy Andrea de Lima 🎨", True),
        ("Mi nombre es Andreita", True),
        ("Andy | Photographer", True),
        ("Soy Andre, músico", True),
        ("Diseñadora gráfica | Lima, Perú", False),
        ("Just a random bio without the name", False),
        ("", False),
    ])
    def test_biography_detection(self, mock_args_ella_enabled, biography, expected_match):
        """Test that names are detected in biography text."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        # Use a non-matching username to test biography detection specifically
        is_match, _ = filter_instance.is_ella_target("random_user_123", biography)
        
        assert is_match == expected_match

    def test_username_takes_priority_over_biography(self, mock_args_ella_enabled):
        """Test that if name is in both username and bio, username match is returned first."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        # Both username and bio contain the name
        is_match, matched_name = filter_instance.is_ella_target(
            "andrea_lima", "Hola soy Andrea"
        )
        
        assert is_match is True
        # The match should come from username (first checked)
        assert matched_name == "Andrea"

    # -------------------------------------------------------------------------
    # Edge Cases Tests
    # -------------------------------------------------------------------------
    
    def test_empty_username(self, mock_args_ella_enabled):
        """Test handling of empty username."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, matched_name = filter_instance.is_ella_target("", "Soy Andrea")
        
        # Should still match in biography
        assert is_match is True

    def test_empty_biography(self, mock_args_ella_enabled):
        """Test handling of empty biography."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, matched_name = filter_instance.is_ella_target("andrea_lima", "")
        
        assert is_match is True

    def test_none_username(self, mock_args_ella_enabled):
        """Test handling of None username."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        # The function handles None by converting to empty string
        is_match, _ = filter_instance.is_ella_target(None, "Soy Andrea")
        
        assert is_match is True

    def test_none_biography(self, mock_args_ella_enabled):
        """Test handling of None biography."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, _ = filter_instance.is_ella_target("andrea_user", None)
        
        assert is_match is True

    def test_unicode_in_username(self, mock_args_ella_enabled):
        """Test handling of unicode characters in username."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, _ = filter_instance.is_ella_target("áñdréá_ユーザー", "")
        
        # Should not match because accented characters differ
        assert is_match is False

    def test_unicode_in_biography(self, mock_args_ella_enabled):
        """Test handling of unicode characters in biography."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        is_match, _ = filter_instance.is_ella_target(
            "random_user", "🎨 Artista Andrea 🎨 Lima, Perú 🇵🇪"
        )
        
        assert is_match is True

    def test_very_long_username(self, mock_args_ella_enabled):
        """Test handling of very long username."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        long_username = "a" * 100 + "andrea" + "b" * 100
        is_match, _ = filter_instance.is_ella_target(long_username, "")
        
        assert is_match is True

    def test_very_long_biography(self, mock_args_ella_enabled):
        """Test handling of very long biography."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        long_bio = "Lorem ipsum " * 100 + "Andrea" + " dolor sit amet " * 100
        is_match, _ = filter_instance.is_ella_target("random_user", long_bio)
        
        assert is_match is True

    # -------------------------------------------------------------------------
    # Disabled/Missing Config Tests
    # -------------------------------------------------------------------------
    
    def test_ella_disabled_returns_false(self, mock_args_ella_disabled):
        """Test that disabled ELLA targeting always returns False."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_disabled)
        is_match, matched_name = filter_instance.is_ella_target("andrea_lima", "Soy Andrea")
        
        assert is_match is False
        assert matched_name == ""

    def test_missing_target_name_returns_false(self):
        """Test that missing target name returns False."""
        args = create_mock_args(ella_enabled=True, ella_name=None, ella_variations=[])
        filter_instance = create_mock_filter_with_ella(args)
        is_match, matched_name = filter_instance.is_ella_target("andrea_lima", "")
        
        assert is_match is False
        assert matched_name == ""

    def test_no_variations_only_matches_primary_name(self, mock_args_ella_no_variations):
        """Test that with no variations, only the primary name matches."""
        filter_instance = create_mock_filter_with_ella(mock_args_ella_no_variations)
        
        # Primary name should match
        is_match, _ = filter_instance.is_ella_target("andrea_user", "")
        assert is_match is True
        
        # Variations should NOT match
        is_match, _ = filter_instance.is_ella_target("andre_user", "")
        assert is_match is False


class TestEllaNombreReplacement:
    """Tests for {{nombre}} variable replacement."""

    def test_single_replacement(self):
        """Test single {{nombre}} replacement."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "Hola {{nombre}}! Bienvenida"
        result = _replace_nombre_variable(text, "Andrea")
        
        assert result == "Hola Andrea! Bienvenida"

    def test_multiple_replacements(self):
        """Test multiple {{nombre}} replacements in same message."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "{{nombre}}, hola {{nombre}}! Qué tal {{nombre}}?"
        result = _replace_nombre_variable(text, "Andrea")
        
        assert result == "Andrea, hola Andrea! Qué tal Andrea?"

    def test_replacement_preserves_surrounding_text(self):
        """Test that replacement preserves surrounding text."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "Antes {{nombre}} después"
        result = _replace_nombre_variable(text, "Andrea")
        
        assert result == "Antes Andrea después"

    def test_replacement_with_emojis(self):
        """Test replacement works with emojis nearby."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "🎉 {{nombre}}! 💃 Fiesta para {{nombre}} 🎊"
        result = _replace_nombre_variable(text, "Andrea")
        
        assert result == "🎉 Andrea! 💃 Fiesta para Andrea 🎊"

    def test_no_replacement_when_placeholder_absent(self):
        """Test that text without {{nombre}} is unchanged."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "Hola! Bienvenida a la fiesta"
        result = _replace_nombre_variable(text, "Andrea")
        
        assert result == text

    def test_placeholder_case_sensitivity(self):
        """Test that placeholder is case-sensitive (only {{nombre}} works)."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        # Different cases should NOT be replaced
        text1 = "Hola {{NOMBRE}}!"
        text2 = "Hola {{Nombre}}!"
        text3 = "Hola {{NoMbRe}}!"
        
        assert _replace_nombre_variable(text1, "Andrea") == text1
        assert _replace_nombre_variable(text2, "Andrea") == text2
        assert _replace_nombre_variable(text3, "Andrea") == text3

    def test_replacement_with_special_characters_in_name(self):
        """Test replacement with special characters in the name."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "Hola {{nombre}}!"
        result = _replace_nombre_variable(text, "María José")
        
        assert result == "Hola María José!"

    def test_empty_name_replacement(self):
        """Test replacement with empty name."""
        from GramAddict.core.interaction import _replace_nombre_variable
        
        text = "Hola {{nombre}}!"
        result = _replace_nombre_variable(text, "")
        
        assert result == "Hola !"


class TestEllaMessageLoading:
    """Tests for loading ELLA-specific messages and comments."""

    def test_load_ella_message_when_target(self, temp_account_folder, mock_args_ella_enabled):
        """Test that ELLA messages are loaded when is_ella_target is True."""
        interaction_module.args = mock_args_ella_enabled
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_message
            
            message = load_random_message("test_user", is_ella_target=True, ella_name="Andrea")
            
            assert message is not None
            # The message should contain "Andrea" (replaced from {{nombre}})
            assert "Andrea" in message

    def test_load_regular_message_when_not_target(self, temp_account_folder):
        """Test that regular messages are loaded when is_ella_target is False."""
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_message
            
            message = load_random_message("test_user", is_ella_target=False)
            
            assert message is not None
            # Regular messages don't contain {{nombre}} or Andrea
            assert "{{nombre}}" not in message

    def test_fallback_to_regular_messages_when_ella_files_missing(
        self, temp_account_folder_no_ella_files
    ):
        """Test fallback to regular messages when ELLA files don't exist."""
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", 
                   os.path.join(temp_account_folder_no_ella_files, "accounts")):
            from GramAddict.core.interaction import load_random_message
            
            # When ELLA files don't exist but default files do, 
            # _ensure_ella_files_exist creates them
            message = load_random_message("test_user", is_ella_target=True, ella_name="Andrea")
            
            # Should still return a message (either from created file or fallback)
            assert message is not None

    def test_load_ella_comment_photo(self, temp_account_folder, mock_args_ella_enabled):
        """Test loading ELLA comment for PHOTO media type."""
        interaction_module.args = mock_args_ella_enabled
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_comment
            from GramAddict.core.views import MediaType
            
            comment = load_random_comment(
                "test_user", MediaType.PHOTO, is_ella_target=True, ella_name="Andrea"
            )
            
            assert comment is not None
            assert "Andrea" in comment

    def test_load_ella_comment_video(self, temp_account_folder, mock_args_ella_enabled):
        """Test loading ELLA comment for VIDEO media type."""
        interaction_module.args = mock_args_ella_enabled
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_comment
            from GramAddict.core.views import MediaType
            
            comment = load_random_comment(
                "test_user", MediaType.VIDEO, is_ella_target=True, ella_name="Andrea"
            )
            
            assert comment is not None
            assert "Andrea" in comment

    def test_load_ella_comment_carousel(self, temp_account_folder, mock_args_ella_enabled):
        """Test loading ELLA comment for CAROUSEL media type."""
        interaction_module.args = mock_args_ella_enabled
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_comment
            from GramAddict.core.views import MediaType
            
            comment = load_random_comment(
                "test_user", MediaType.CAROUSEL, is_ella_target=True, ella_name="Andrea"
            )
            
            assert comment is not None
            assert "Andrea" in comment

    def test_load_regular_comment_when_not_target(self, temp_account_folder):
        """Test that regular comments are loaded when is_ella_target is False."""
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", os.path.join(temp_account_folder, "accounts")):
            from GramAddict.core.interaction import load_random_comment
            from GramAddict.core.views import MediaType
            
            comment = load_random_comment("test_user", MediaType.PHOTO, is_ella_target=False)
            
            assert comment is not None
            assert "{{nombre}}" not in comment


class TestEllaFileCreation:
    """Tests for automatic ELLA file creation from defaults."""

    def test_creates_ella_pm_file_from_default(self, temp_account_folder_no_ella_files):
        """Test that ELLA PM file is created from default when missing."""
        accounts_path = os.path.join(temp_account_folder_no_ella_files, "accounts")
        ella_pm_path = os.path.join(accounts_path, "test_user", "pm_ella.txt")
        
        assert not os.path.exists(ella_pm_path)
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import _ensure_ella_files_exist
            
            _ensure_ella_files_exist("test_user")
            
            assert os.path.exists(ella_pm_path)
            
            with open(ella_pm_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Should contain {{nombre}} (added during creation)
                assert "{{nombre}}" in content

    def test_creates_ella_comments_file_from_default(self, temp_account_folder_no_ella_files):
        """Test that ELLA comments file is created from default when missing."""
        accounts_path = os.path.join(temp_account_folder_no_ella_files, "accounts")
        ella_comments_path = os.path.join(accounts_path, "test_user", "comments_ella.txt")
        
        assert not os.path.exists(ella_comments_path)
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import _ensure_ella_files_exist
            
            _ensure_ella_files_exist("test_user")
            
            assert os.path.exists(ella_comments_path)
            
            with open(ella_comments_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert "{{nombre}}" in content

    def test_does_not_overwrite_existing_ella_files(self, temp_account_folder):
        """Test that existing ELLA files are not overwritten."""
        accounts_path = os.path.join(temp_account_folder, "accounts")
        ella_pm_path = os.path.join(accounts_path, "test_user", "pm_ella.txt")
        
        # Read original content
        with open(ella_pm_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import _ensure_ella_files_exist
            
            _ensure_ella_files_exist("test_user")
            
            # Content should be unchanged
            with open(ella_pm_path, "r", encoding="utf-8") as f:
                new_content = f.read()
                assert new_content == original_content


class TestEllaStorageTracking:
    """Tests for ELLA target tracking in storage."""

    def test_mark_ella_target(self):
        """Test that mark_ella_target correctly flags a user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the account structure
            account_path = os.path.join(tmpdir, "test_user")
            os.makedirs(account_path)
            
            with patch("GramAddict.core.storage.ACCOUNTS", tmpdir):
                from GramAddict.core.storage import Storage
                
                storage = Storage("test_user")
                
                # Initially, user should not be in interacted_users
                assert "andrea_lima" not in storage.interacted_users
                
                # Mark as ELLA target
                storage.mark_ella_target("andrea_lima")
                
                # User should now have ella_target flag
                assert "andrea_lima" in storage.interacted_users
                assert storage.interacted_users["andrea_lima"]["ella_target"] is True

    def test_mark_ella_target_existing_user(self):
        """Test marking an already-interacted user as ELLA target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            account_path = os.path.join(tmpdir, "test_user")
            os.makedirs(account_path)
            
            with patch("GramAddict.core.storage.ACCOUNTS", tmpdir):
                from GramAddict.core.storage import Storage
                
                storage = Storage("test_user")
                
                # Add user with some existing data
                storage.interacted_users["andrea_lima"] = {
                    "followed": True,
                    "liked": 3,
                }
                
                # Mark as ELLA target
                storage.mark_ella_target("andrea_lima")
                
                # Should preserve existing data and add ella_target
                assert storage.interacted_users["andrea_lima"]["followed"] is True
                assert storage.interacted_users["andrea_lima"]["liked"] == 3
                assert storage.interacted_users["andrea_lima"]["ella_target"] is True


class TestEllaStorageConstants:
    """Tests for ELLA-related storage constants."""

    def test_ella_filename_constants_exist(self):
        """Test that ELLA filename constants are defined."""
        from GramAddict.core import storage
        
        assert hasattr(storage, "FILENAME_ELLA_MESSAGES")
        assert hasattr(storage, "FILENAME_ELLA_COMMENTS")
        assert storage.FILENAME_ELLA_MESSAGES == "pm_ella.txt"
        assert storage.FILENAME_ELLA_COMMENTS == "comments_ella.txt"


class TestEllaIntegration:
    """Integration tests for full ELLA targeting flow."""

    def test_full_flow_matching_username(self, temp_account_folder, mock_args_ella_enabled):
        """Test complete flow: username match → ELLA message → name replacement."""
        accounts_path = os.path.join(temp_account_folder, "accounts")
        
        # Setup filter
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        
        # Setup interaction module
        interaction_module.args = mock_args_ella_enabled
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import load_random_message
            
            # Step 1: Check if user is ELLA target
            # Note: "andrea" matches first in the variations list before "andreita"
            is_ella, matched_name = filter_instance.is_ella_target("andrea_lima", "")
            
            assert is_ella is True
            assert matched_name.lower() == "andrea"
            
            # Step 2: Load ELLA message with replacement
            message = load_random_message(
                "test_user", 
                is_ella_target=True, 
                ella_name=matched_name
            )
            
            assert message is not None
            # Should contain the configured name (Andrea), not the matched variation
            assert "Andrea" in message

    def test_full_flow_matching_biography(self, temp_account_folder, mock_args_ella_enabled):
        """Test complete flow: biography match → ELLA message → name replacement."""
        accounts_path = os.path.join(temp_account_folder, "accounts")
        
        # Setup filter
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        
        # Setup interaction module
        interaction_module.args = mock_args_ella_enabled
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import load_random_message
            
            is_ella, matched_name = filter_instance.is_ella_target(
                "random_user_123", "Hola soy Andy, fotógrafa de Lima"
            )
            
            assert is_ella is True
            assert matched_name.lower() == "andy"
            
            message = load_random_message(
                "test_user",
                is_ella_target=True,
                ella_name=matched_name
            )
            
            assert message is not None
            assert "Andrea" in message

    def test_full_flow_non_matching_user(self, temp_account_folder, mock_args_ella_enabled):
        """Test that non-matching users get regular treatment."""
        accounts_path = os.path.join(temp_account_folder, "accounts")
        
        # Setup filter
        filter_instance = create_mock_filter_with_ella(mock_args_ella_enabled)
        
        with patch("GramAddict.core.interaction.storage.ACCOUNTS", accounts_path):
            from GramAddict.core.interaction import load_random_message
            
            is_ella, matched_name = filter_instance.is_ella_target(
                "maria_garcia", "Fotógrafa profesional"
            )
            
            assert is_ella is False
            assert matched_name == ""
            
            # Should load regular message
            message = load_random_message("test_user", is_ella_target=False)
            
            assert message is not None
            # Regular messages don't contain Andrea
            assert "Andrea" not in message or "{{nombre}}" in message


class TestEllaConfigurationArguments:
    """Tests for ELLA configuration arguments."""

    def test_ella_arguments_defined(self):
        """Test that ELLA arguments are properly defined in core_arguments."""
        from GramAddict.plugins.core_arguments import CoreArguments
        
        core_args = CoreArguments()
        arg_names = [arg["arg"] for arg in core_args.arguments]
        
        assert "--ella-targeting-enabled" in arg_names
        assert "--ella-targeting-name" in arg_names
        assert "--ella-targeting-variations" in arg_names

    def test_ella_enabled_is_store_true(self):
        """Test that ella-targeting-enabled uses store_true action."""
        from GramAddict.plugins.core_arguments import CoreArguments
        
        core_args = CoreArguments()
        
        for arg in core_args.arguments:
            if arg["arg"] == "--ella-targeting-enabled":
                assert arg.get("action") == "store_true"
                break
        else:
            pytest.fail("--ella-targeting-enabled argument not found")

    def test_ella_variations_accepts_multiple(self):
        """Test that ella-targeting-variations accepts multiple values."""
        from GramAddict.plugins.core_arguments import CoreArguments
        
        core_args = CoreArguments()
        
        for arg in core_args.arguments:
            if arg["arg"] == "--ella-targeting-variations":
                assert arg.get("nargs") == "+"
                break
        else:
            pytest.fail("--ella-targeting-variations argument not found")
