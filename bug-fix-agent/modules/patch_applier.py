from pathlib import Path
import shutil
from datetime import datetime


class PatchApplicationResult:

    def __init__(
        self,
        success=False,
        message="",
        source_path="",
        backup_path="",
        replacements=0,
    ):
        self.success = success
        self.message = message
        self.source_path = source_path
        self.backup_path = backup_path
        self.replacements = replacements

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"

        return f"""
======================================================================
                    PATCH APPLICATION
======================================================================

Status       : {status}
Message      : {self.message}
Source       : {self.source_path}
Backup       : {self.backup_path}
Replacements : {self.replacements}

======================================================================
"""


class PatchApplier:

    def __init__(self, backup_dir_name=".vamp_backup"):
        self.backup_dir_name = backup_dir_name

    def apply(self, source_path, old_code, new_code):

        source = Path(source_path).resolve()

        print()
        print("=" * 70)
        print("                    PATCH APPLICATION")
        print("=" * 70)

        print(f"Source : {source}")

        if not source.exists():
            return self._failure(
                "Source file does not exist."
            )

        if not source.is_file():
            return self._failure(
                "Source path is not a regular file."
            )

        if not old_code or not old_code.strip():
            return self._failure(
                "old_code is empty."
            )

        if not new_code or not new_code.strip():
            return self._failure(
                "new_code is empty."
            )

        if old_code == new_code:
            return self._failure(
                "old_code and new_code are identical."
            )

        try:
            original_text = source.read_text(
                encoding="utf-8"
            )
        except Exception as exc:
            return self._failure(
                f"Unable to read source: {exc}"
            )

        occurrence_count = original_text.count(old_code)

        print(
            f"Exact old_code matches found : {occurrence_count}"
        )

        if occurrence_count == 0:
            return self._failure(
                "old_code was not found in source."
            )

        if occurrence_count > 1:
            return self._failure(
                "old_code occurs more than once. "
                "Refusing ambiguous replacement."
            )

        try:
            backup_path = self.create_backup(source)
        except Exception as exc:
            return self._failure(
                f"Unable to create backup: {exc}"
            )

        print(f"Backup created : {backup_path}")

        modified_text = original_text.replace(
            old_code,
            new_code,
            1,
        )

        if modified_text == original_text:
            self.restore_backup(source, backup_path)

            return self._failure(
                "Replacement produced no change.",
                backup_path,
            )

        if old_code in modified_text:
            self.restore_backup(source, backup_path)

            return self._failure(
                "old_code still exists after replacement.",
                backup_path,
            )

        if new_code not in modified_text:
            self.restore_backup(source, backup_path)

            return self._failure(
                "new_code was not found after replacement.",
                backup_path,
            )

        try:
            source.write_text(
                modified_text,
                encoding="utf-8",
            )
        except Exception as exc:

            self.restore_backup(source, backup_path)

            return self._failure(
                f"Write failed. Original restored: {exc}",
                backup_path,
            )

        try:
            final_text = source.read_text(
                encoding="utf-8"
            )
        except Exception as exc:

            self.restore_backup(source, backup_path)

            return self._failure(
                f"Verification failed. Original restored: {exc}",
                backup_path,
            )

        if old_code in final_text:
            self.restore_backup(source, backup_path)

            return self._failure(
                "old_code still exists after writing. "
                "Original restored.",
                backup_path,
            )

        if new_code not in final_text:
            self.restore_backup(source, backup_path)

            return self._failure(
                "new_code missing after writing. "
                "Original restored.",
                backup_path,
            )

        print()
        print("✅ Patch successfully applied.")
        print("✅ Exact replacement verified.")

        return PatchApplicationResult(
            success=True,
            message="Patch applied and verified successfully.",
            source_path=str(source),
            backup_path=str(backup_path),
            replacements=1,
        )

    def create_backup(self, source):

        project_root = self.find_project_root(source)

        backup_dir = (
            project_root / self.backup_dir_name
        )

        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        backup_path = (
            backup_dir /
            f"{source.name}.{timestamp}.bak"
        )

        shutil.copy2(
            source,
            backup_path,
        )

        return backup_path

    @staticmethod
    def find_project_root(source):

        current = source.parent

        markers = [
            "settings.gradle",
            "settings.gradle.kts",
            "build.gradle",
            "build.gradle.kts",
            "gradlew",
        ]

        while True:

            for marker in markers:
                if (current / marker).exists():
                    return current

            parent = current.parent

            if parent == current:
                break

            current = parent

        return source.parent

    @staticmethod
    def restore_backup(source, backup_path):

        if not backup_path:
            return False

        backup = Path(backup_path)

        if not backup.exists():
            return False

        try:
            shutil.copy2(
                backup,
                source,
            )

            print("✅ Original source restored.")

            return True

        except Exception as exc:

            print(
                f"❌ Restore failed: {exc}"
            )

            return False

    @staticmethod
    def _failure(message, backup_path=""):

        print(f"❌ {message}")

        return PatchApplicationResult(
            success=False,
            message=message,
            backup_path=str(backup_path),
        )
