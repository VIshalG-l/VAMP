import shutil
import difflib
from pathlib import Path


# ==========================================================
# Backup
# ==========================================================

def backup_file(path):
    """
    Create a backup of the source file.
    """

    path = Path(path)

    backup = path.with_suffix(path.suffix + ".bak")

    shutil.copy2(path, backup)

    return backup


def restore_backup(path):
    """
    Restore backup if available.
    """

    path = Path(path)

    backup = path.with_suffix(path.suffix + ".bak")

    if backup.exists():
        shutil.copy2(backup, path)
        return True

    return False


# ==========================================================
# Diff
# ==========================================================

def show_diff(old_text, new_text):
    """
    Display patch diff.
    """

#    print("\n" + "=" * 60)
#    print("PATCH DIFF")
#    print("=" * 60)

    diff = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile="Original",
        tofile="Patched",
        lineterm=""
    )

#    for line in diff:
#        print(line)


# ==========================================================
# Statistics
# ==========================================================

def patch_statistics(old_text, new_text):

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    changed = abs(len(new_lines) - len(old_lines))

    chars = len(new_text) - len(old_text)

    # Statistics are retained internally.
    # Terminal output is intentionally suppressed.
    return {
        "line_delta": changed,
        "character_diff": chars,
    }


# ==========================================================
# Validation
# ==========================================================

def validate_patch(patch):

    if not patch.has_patch():
        return False, "LLM did not generate a patch."

    if not patch.old_code.strip():
        return False, "old_code is empty."

    if not patch.new_code.strip():
        return False, "new_code is empty."

    if patch.old_code.strip() == patch.new_code.strip():
        return False, "old_code and new_code are identical."

    return True, ""


# ==========================================================
# Apply Patch
# ==========================================================

def apply_patch(path, patch):
    """
    Apply AI-generated patch.

    Returns:
        (success, message)
    """

    valid, msg = validate_patch(patch)

    if not valid:
        return False, msg

    path = Path(path)

    if not path.exists():
        return False, f"Source file not found: {path}"

    backup_file(path)

    try:

        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        source = source.replace("\r\n", "\n")

        old = patch.old_code.replace("\r\n", "\n").strip()
        new = patch.new_code.replace("\r\n", "\n").strip()

        occurrences = source.count(old)

        if occurrences == 0:

            restore_backup(path)

            return (
                False,
                "Old code snippet was not found in the source file."
            )

        if occurrences > 1:

            restore_backup(path)

            return (
                False,
                f"Patch is ambiguous ({occurrences} matches found)."
            )

        updated = source.replace(
            old,
            new,
            1
        )

        show_diff(source, updated)

        patch_statistics(source, updated)

        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)

        print("\n✅ Patch applied successfully.\n")

        return (
            True,
            f"Patch applied successfully to {path.name}"
        )

    except Exception as e:

        restore_backup(path)

        return (
            False,
            f"Patch failed: {e}"
        )


# ==========================================================
# Rollback
# ==========================================================

def rollback(path):
    """
    Restore original file.
    """

    success = restore_backup(path)

    if success:

        print("\nRollback completed.\n")

        return (
            True,
            "Rollback successful."
        )

    return (
        False,
        "Backup file not found."
    )
