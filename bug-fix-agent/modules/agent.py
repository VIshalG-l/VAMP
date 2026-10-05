from pathlib import Path

from config import MAX_RETRIES

from modules.project_resolver import ProjectResolver
from modules.failure_evidence import FailureEvidenceCollector
from modules.evidence_analyzer import EvidenceAnalyzer
from modules.code_search import (
    find_source,
    find_native_source,
)
from modules.file_reader import read_context
from modules.llm import ask_llm
from modules.patch_validator import PatchValidator
from modules.patch_applier import PatchApplier
from modules.builder import build_project
from modules.failure_reproducer import FailureReproducer


class BugFixAgent:
    """
    VAMP Android failure diagnosis and AI repair agent.

    Current pipeline:

        Incident
            |
            v
        FailureEvidenceCollector
            |
            v
        FailureEvidence
            |
            v
        EvidenceAnalyzer
            |
            v
        ProjectResolver
            |
            v
        Source Discovery
            |
            v
        Source Context
            |
            v
        Gemini RCA
            |
            v
        AI Patch Proposal
            |
            v
        Patch Validator
            |
            v
        ACCEPT / REJECT

    IMPORTANT:

        This version DOES NOT yet:

            - modify source files
            - apply AI patches
            - build the project
            - install an APK
            - launch an APK
            - verify the patch
            - rollback source files

        The LLM is currently used for:

            RCA + patch proposal

        The generated patch is validated before any future
        source modification is allowed.
    """

    def __init__(
        self,
        incident,
        source_roots=None,
        max_retries=None,
    ):
        self.incident = incident

        self.source_roots = source_roots

        self.max_retries = (
            max_retries
            if max_retries is not None
            else MAX_RETRIES
        )

        self.resolver = ProjectResolver(
            source_roots=source_roots
        )

        self.evidence_collector = (
            FailureEvidenceCollector(
                serial=getattr(
                    incident,
                    "device_serial",
                    None,
                )
            )
        )

        self.evidence_analyzer = (
            EvidenceAnalyzer()
        )

        # --------------------------------------------------------
        # Patch validator
        # --------------------------------------------------------

        self.patch_validator = (
            PatchValidator()
        )

        self.patch_applier = (
            PatchApplier()
        )

        self.workspace = None
        self.module = None

        self.evidence = None
        self.analysis = None

        self.source = None
        self.context = None

        # AI result
        self.patch = None

        # Patch validation result
        self.patch_validation = None

        # Patch application result
        self.patch_application = None

        # Build result
        self.build_success = False
        self.apk_path = None
        self.build_logs = ""

    # ============================================================
    # STEP 9 - BUILD PATCHED PROJECT
    # ============================================================

    def build_patched_project(self):

        print()
        print("=" * 70)
        print("                 BUILD PATCHED PROJECT")
        print("=" * 70)

        if not self.workspace:

            print()
            print(
                "❌ Cannot build: workspace is missing."
            )

            self.build_success = False
            self.apk_path = None
            self.build_logs = "Workspace is missing."

            return False

        print()
        print(
            "Workspace :",
            self.workspace
        )

        print()
        print(
            "→ Running project build..."
        )

        try:

            build_ok, apk_path, build_logs = (
                build_project(
                    self.workspace
                )
            )

        except Exception as exc:

            print()
            print(
                "❌ Build system failed unexpectedly:"
            )

            print(exc)

            self.build_success = False
            self.apk_path = None
            self.build_logs = str(exc)

            self.restore_failed_patch()

            return False

        self.build_success = bool(
            build_ok
        )

        self.apk_path = apk_path

        self.build_logs = (
            build_logs or ""
        )

        print()

        print(
            "Build Result :",
            "SUCCESS"
            if self.build_success
            else "FAILED"
        )

        if self.apk_path:

            print(
                "APK Path     :",
                self.apk_path
            )

        # --------------------------------------------------------
        # A build is not considered successful unless an APK
        # was actually generated.
        # --------------------------------------------------------

        if self.build_success and not self.apk_path:

            print()
            print(
                "❌ Build reported success but no APK was found."
            )

            self.build_success = False

        if not self.build_success:

            print()
            print(
                "❌ Patched project build failed."
            )

            print()
            print(
                "========== BUILD LOG =========="
            )

            print(
                self.build_logs
            )

            self.restore_failed_patch()

            return False

        print()
        print(
            "✅ Patched project built successfully."
        )

        return True


    # ============================================================
    # RESTORE PATCH AFTER BUILD FAILURE
    # ============================================================

    def restore_failed_patch(self):

        print()
        print(
            "→ Restoring original source after build failure..."
        )

        if not self.patch_application:

            print()
            print(
                "❌ Patch application result is missing."
            )

            return False

        source_path = (
            self.patch_application.source_path
        )

        backup_path = (
            self.patch_application.backup_path
        )

        if not source_path:

            print()
            print(
                "❌ Original source path is missing."
            )

            return False

        if not backup_path:

            print()
            print(
                "❌ Backup path is missing."
            )

            return False

        try:

            restored = (
                self.patch_applier.restore_backup(
                    source_path,
                    backup_path
                )
            )

        except Exception as exc:

            print()
            print(
                "❌ Source restoration failed:"
            )

            print(exc)

            return False

        if restored:

            print()
            print(
                "✅ Original source restored."
            )

            return True

        print()
        print(
            "❌ Original source could not be restored."
        )

        return False


    # ============================================================
    # MAIN PIPELINE
    # ============================================================

    def run(self):

        print()
        print("=" * 70)
        print("             VAMP DIAGNOSIS PIPELINE")
        print("=" * 70)

        self.print_incident()

        # --------------------------------------------------------
        # STEP 1
        # Collect device evidence
        # --------------------------------------------------------

        print()
        print("[1] Collecting failure evidence...")

        try:

            self.evidence = (
                self.evidence_collector.collect(
                    self.incident
                )
            )

        except Exception as exc:

            print()
            print(
                "❌ Failure evidence collection failed:"
            )

            print(exc)

            return False

        if not self.evidence:

            print()
            print(
                "❌ No failure evidence was collected."
            )

            return False

        print()
        print(
            "✅ Failure evidence collected."
        )

        # --------------------------------------------------------
        # STEP 2
        # Analyze evidence
        # --------------------------------------------------------

        print()
        print("[2] Analyzing failure evidence...")

        try:

            self.analysis = (
                self.evidence_analyzer.analyze(
                    self.evidence
                )
            )

        except Exception as exc:

            print()
            print(
                "❌ Evidence analysis failed:"
            )

            print(exc)

            return False

        # --------------------------------------------------------
        # Correct unreliable ANR reason
        # --------------------------------------------------------

        self.correct_analysis_from_incident()

        self.evidence_analyzer.print_analysis(
            self.analysis
        )

        print()
        print(
            "✅ Failure evidence analyzed."
        )

        # --------------------------------------------------------
        # STEP 3
        # Resolve source project
        # --------------------------------------------------------

        print()
        print("[3] Resolving source project...")

        package = (
            self.analysis.package
            or getattr(
                self.incident,
                "package",
                "",
            )
        )

        if not package:

            print()
            print(
                "❌ Package could not be identified."
            )

            return False

        resolved = self.resolve_project(
            package
        )

        if not resolved:

            print()
            print(
                "❌ Unable to resolve source project."
            )

            return False

        self.workspace = resolved[
            "workspace"
        ]

        self.module = resolved.get(
            "module"
        )

        print()
        print(
            "✅ Workspace resolved:"
        )

        print(
            self.workspace
        )

        if self.module:

            print(
                "Module:"
            )

            print(
                self.module
            )

        # --------------------------------------------------------
        # STEP 4
        # Find source
        # --------------------------------------------------------

        print()
        print(
            "[4] Locating relevant source code..."
        )

        self.source = self.locate_source()

        if not self.source:

            print()
            print(
                "⚠ No exact source file could be identified."
            )

            print()
            print(
                "The failure is diagnosed, but "
                "AI source-level repair cannot safely continue."
            )

            self.print_final_diagnosis(
                source_found=False
            )

            return True

        print()
        print(
            "✅ Candidate source found:"
        )

        print(
            self.source["path"]
        )

        # --------------------------------------------------------
        # STEP 5
        # Read source context
        # --------------------------------------------------------

        print()
        print("[5] Reading source context...")

        try:

            self.context = (
                self.read_source_context()
            )

        except Exception as exc:

            print()
            print(
                "⚠ Source context could not be loaded:"
            )

            print(exc)

            self.print_final_diagnosis(
                source_found=True,
                context_loaded=False,
            )

            return True

        if not self.context:

            print()
            print(
                "⚠ Source context is empty."
            )

            self.print_final_diagnosis(
                source_found=True,
                context_loaded=False,
            )

            return True

        print()
        print("✓ Source context loaded.")

        print(
            "File:",
            self.context.get(
                "file",
                self.source["path"],
            )
        )

        print(
            "Lines:",
            self.context.get(
                "total_lines",
                "unknown",
            )
        )

        # --------------------------------------------------------
        # STEP 6
        # Gemini RCA + Patch
        # --------------------------------------------------------

        print()
        print(
            "[6] Generating AI root-cause analysis..."
        )

        try:

            self.patch = (
                self.generate_ai_analysis()
            )

        except Exception as exc:

            print()
            print(
                "⚠ AI analysis failed:"
            )

            print(exc)

            self.print_final_diagnosis(
                source_found=True,
                context_loaded=True,
            )

            return True

        if not self.patch:

            print()
            print(
                "⚠ AI did not return an analysis."
            )

            self.print_final_diagnosis(
                source_found=True,
                context_loaded=True,
            )

            return True

        print()
        print(
            "✅ AI root-cause analysis completed."
        )

        self.print_ai_result()

        # --------------------------------------------------------
        # STEP 7
        # Validate AI patch
        # --------------------------------------------------------

        # --------------------------------------------------------
        # STEP 7
        #
        # A diagnosis may legitimately determine that no patch
        # is required. This is a successful diagnosis and must
        # not be treated as a PatchValidator rejection.
        # --------------------------------------------------------

        if not self.patch.patch_required:

            print()
            print(
                "ℹ AI determined that no source patch is required."
            )

            print()
            print(
                "✅ Diagnosis completed without modifying source."
            )

            self.print_pipeline_status(
                patch_generated=False,
                patch_valid=True,
            )

            return True

        print()
        print(
            "[7] Validating AI patch..."
        )

        validation_ok = (
            self.validate_ai_patch()
        )

        if not validation_ok:

            print()
            print(
                "⚠ AI patch was rejected by the "
                "PatchValidator."
            )

            print()
            print(
                "The source file will NOT be modified."
            )

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=False,
            )

            return True

        print()
        print(
            "✅ AI patch passed validation."
        )

        # --------------------------------------------------------
        # STEP 8
        # Apply validated patch
        # --------------------------------------------------------

        print()
        print(
            "[8] Applying validated AI patch..."
        )

        patch_applied = (
            self.apply_ai_patch()
        )

        if not patch_applied:

            print()
            print(
                "⚠ Patch application failed."
            )

            print()
            print(
                "The source was not left in an unsafe "
                "partially modified state."
            )

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=False,
            )

            return True

        print()
        print(
            "✅ AI patch applied successfully."
        )

        # --------------------------------------------------------
        # STEP 9
        # Build patched project
        # --------------------------------------------------------

        print()
        print("[9] Building patched project...")

        if not self.build_patched_project():
            print()
            print("❌ Build failed.")
            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=True,
                build_success=False,
                verification_status="NOT RUN",
                rollback_status="COMPLETED",
            )
            return False

        print()
        print("✅ Patched project build completed.")

        # --------------------------------------------------------
        # STEP 10
        # Install generated APK
        # --------------------------------------------------------

        print()
        print("[10] Installing generated APK...")

        if not self.install_patched_apk():
            print()
            print("❌ APK installation failed.")
            print("→ Rolling back source patch...")

            rollback_ok = self.restore_failed_patch()

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=True,
                build_success=True,
                install_success=False,
                verification_status="FAILED",
                rollback_status=(
                    "SUCCESS"
                    if rollback_ok
                    else "FAILED"
                ),
            )
            return False

        print()
        print("✅ APK installation completed.")

        # --------------------------------------------------------
        # STEP 11
        # Launch application
        # --------------------------------------------------------

        print()
        print("[11] Launching patched application...")

        if not self.launch_patched_app():
            print()
            print("❌ Patched application launch failed.")
            print("→ Rolling back source patch...")

            rollback_ok = self.restore_failed_patch()

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=True,
                build_success=True,
                install_success=True,
                launch_success=False,
                verification_status="FAILED",
                rollback_status=(
                    "SUCCESS"
                    if rollback_ok
                    else "FAILED"
                ),
            )
            return False

        print()
        print("✅ Patched application launched successfully.")

        # --------------------------------------------------------
        # STEP 12
        # Run automated tests
        # --------------------------------------------------------

        print()
        print("[12] Running automated tests...")

        if not self.run_patched_tests():
            print()
            print("❌ Automated tests failed.")
            print("→ Rolling back source patch...")

            rollback_ok = self.restore_failed_patch()

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=True,
                build_success=True,
                install_success=True,
                launch_success=True,
                tests_success=False,
                verification_status="FAILED",
                rollback_status=(
                    "SUCCESS"
                    if rollback_ok
                    else "FAILED"
                ),
            )
            return False

        print("✓ Tests passed")

        # --------------------------------------------------------
        # STEP 13
        # Runtime verification
        # --------------------------------------------------------

        print()
        print("[13] Verifying patched application...")

        verification_ok = self.verify_patched_application()

        if not verification_ok:
            print()
            print("❌ Runtime verification failed.")
            print("→ Rolling back source patch...")

            rollback_ok = self.restore_failed_patch()

            self.print_pipeline_status(
                patch_generated=True,
                patch_valid=True,
                patch_applied=True,
                build_success=True,
                install_success=True,
                launch_success=True,
                tests_success=True,
                verification_status="FAILED",
                rollback_status=(
                    "SUCCESS"
                    if rollback_ok
                    else "FAILED"
                ),
            )
            return False

        print()
        print("✅ Runtime verification passed.")

        self.print_pipeline_status(
            patch_generated=True,
            patch_valid=True,
            patch_applied=True,
            build_success=True,
            install_success=True,
            launch_success=True,
            tests_success=True,
            verification_status="PASSED",
            rollback_status="NOT REQUIRED",
        )

        print()
        print("=" * 70)
        print("                 VAMP FIX VERIFIED")
        print("=" * 70)
        print("Original failure :", getattr(
            self.incident,
            "bug_type",
            "UNKNOWN"
        ))
        print("Patched source   :", self.source["path"])
        print("Generated APK    :", self.apk_path)
        print("Build            : SUCCESS")
        print("Install          : SUCCESS")
        print("Launch           : SUCCESS")
        print("Tests            : PASSED")
        print("Verification     : PASSED")
        print("=" * 70)

        return True

    # ============================================================
    # INSTALL PATCHED APK
    # ============================================================

    def install_patched_apk(self):

        if not self.apk_path:
            print()
            print("❌ Cannot install: APK path is missing.")
            return False

        apk_path = Path(self.apk_path)

        if not apk_path.exists():
            print()
            print("❌ Cannot install: APK does not exist.")
            print("APK:", apk_path)
            return False

        print()
        print("[10] Installing APK...")

        try:
            from modules.apk_installer import install_apk

            package = (
                getattr(
                    self.incident,
                    "package",
                    "",
                )
                or (
                    getattr(
                        self.analysis,
                        "package",
                        "",
                    )
                    if self.analysis
                    else ""
                )
                or ""
            ).strip()

            if not package:
                print()
                print(
                   "❌ Cannot install: package could not be determined."
                )
                return False

            print(
                "Package:",
                package,
          )

            result = install_apk(
                str(apk_path),
                package=package,
            )
        #try:
         #$   from modules.apk_installer import install_apk

           # result = install_apk(str(apk_path))

        except Exception as exc:
            print()
            print("❌ APK installer failed unexpectedly:")
            print(exc)
            return False

        if isinstance(result, tuple):
            success = bool(result[0])
            message = result[1] if len(result) > 1 else ""
        else:
            success = bool(result)
            message = ""

        if not success:
            print()
            print("❌ APK installation failed.")
            return False

        print("✓ APK installed")

        return True


    # ============================================================
    # LAUNCH PATCHED APPLICATION
    # ============================================================

    def launch_patched_app(self):

        activity = ""

        if self.analysis:
            activity = (
                getattr(
                    self.analysis,
                    "activity",
                    "",
                )
                or ""
            ).strip()

        if not activity:
            print()
            print(
                "❌ Cannot launch: launcher activity "
                "could not be determined."
            )
            return False

        activity_class = (
            self.extract_activity_class(activity)
        )

        if not activity_class:
            print()
            print(
                "❌ Cannot launch: invalid activity:"
            )
            print(activity)
            return False

        package = (
            getattr(
                self.incident,
                "package",
                "",
            )
            or (
                self.analysis.package
                if self.analysis
                else ""
            )
            or ""
        ).strip()

        if not package:
            print()
            print(
                "❌ Cannot launch: package could not "
                "be determined."
            )
            return False

        print()
        print("[11] Launching APK...")

        try:
            from modules.app_launcher import launch_app

            result = launch_app(
                package,
                activity_class,
            )

        except Exception as exc:
            print()
            print("❌ Application launcher failed unexpectedly:")
            print(exc)
            return False

        if isinstance(result, tuple):
            success = bool(result[0])
            message = result[1] if len(result) > 1 else ""
        else:
            success = bool(result)
            message = ""

        if not success:
            print()
            print("❌ Application launch failed.")
            return False

        print("✓ Application launched")

        return True


    # ============================================================
    # RUN AUTOMATED TESTS
    # ============================================================

    def run_patched_tests(self):

        if not self.workspace:
            print()
            print("❌ Cannot run tests: workspace is missing.")
            return False

        print()
        print("[12] Running tests...")

        try:
            from modules.tester import run_tests

            result = run_tests(
                self.workspace
            )

        except Exception as exc:
            print()
            print("❌ Test execution failed unexpectedly:")
            print(exc)
            return False

        if isinstance(result, tuple):
            success = bool(result[0])
            logs = result[1] if len(result) > 1 else ""
        else:
            success = bool(result)
            logs = ""

        if not success:
            print()
            print("❌ Automated tests failed.")
            return False

        print("✓ Tests passed")

        return True


    # ============================================================
    # RUNTIME VERIFICATION
    # ============================================================

    def verify_patched_application(self):

        print()
        print("[13] Verifying fix...")

        package = (
            getattr(
                self.incident,
                "package",
                "",
            )
            or (
                self.analysis.package
                if self.analysis
                else ""
            )
            or ""
        ).strip()

        failure_type = (
            getattr(
                self.incident,
                "bug_type",
                "",
            )
            or (
                self.analysis.failure_type
                if self.analysis
                else ""
            )
            or "UNKNOWN"
        ).strip().upper()

        device_serial = (
            getattr(
                self.incident,
                "device_serial",
                "",
            )
            or ""
        ).strip()

        if not package:

            print()
            print(
                "❌ Cannot verify: "
                "package is unknown."
            )

            return False

        # ----------------------------------------------------
        # Build source context for UI/action correlation
        # ----------------------------------------------------

        source_context = (
            getattr(
                self,
                "context",
                "",
            )
            or ""
        )

        # ----------------------------------------------------
        # Build evidence text
        #
        # Keep this generic because the exact evidence
        # object can differ between failure types.
        # ----------------------------------------------------

        evidence_text_parts = []

        incident_reason = (
            getattr(
                self.incident,
                "reason",
                "",
            )
            or ""
        )

        incident_exception = (
            getattr(
                self.incident,
                "exception",
                "",
            )
            or ""
        )

        incident_thread = (
            getattr(
                self.incident,
                "thread",
                "",
            )
            or ""
        )

        incident_stack = (
            getattr(
                self.incident,
                "stack_trace",
                "",
            )
            or ""
        )

        incident_raw_log = (
            getattr(
                self.incident,
                "raw_log",
                "",
            )
            or ""
        )

        if incident_reason:
            evidence_text_parts.append(
                incident_reason
            )

        if incident_exception:
            evidence_text_parts.append(
                incident_exception
            )

        if incident_thread:
            evidence_text_parts.append(
                incident_thread
            )

        if incident_stack:
            evidence_text_parts.append(
                incident_stack
            )

        if incident_raw_log:
            evidence_text_parts.append(
                incident_raw_log
            )

        # Include collected analysis/evidence when available.
        #
        # We intentionally use getattr() so this remains
        # compatible with different evidence object types.

        for attribute_name in (
            "raw_text",
            "text",
            "logs",
            "raw_log",
            "summary",
            "evidence",
        ):

            value = getattr(
                getattr(
                    self,
                    "evidence",
                    None,
                ),
                attribute_name,
                None,
            )

            if value:
                evidence_text_parts.append(
                    str(value)
                )

        evidence_text = "\n".join(
            evidence_text_parts
        )


        # ----------------------------------------------------
        # Select observation window based on failure type
        # ----------------------------------------------------

        observation_seconds_map = {
            "ANR": 20,
            "JAVA_CRASH": 6,
            "CRASH": 6,
            "NATIVE_CRASH": 10,
            "PROCESS_DEATH": 6,
            "GENERIC": 10,
        }
        observation_seconds = observation_seconds_map.get(
            failure_type,
            10,
        )

        print()
        print(
            "Observation Window :",
           f"{observation_seconds} seconds",
        )
# ----------------------------------------------------
# Create generic FailureReproducer
# ----------------------------------------------------

        print()
        print("=" * 70)
        print("DEBUG: INCIDENT BEFORE FAILURE REPRODUCER")
        print("=" * 70)
        print(
            "Incident object :",
            type(self.incident).__name__
        )
        print(
            "Incident package:",
            repr(getattr(self.incident, "package", None))
        )
        print(
            "Incident process:",
            repr(getattr(self.incident, "process", None))
        )
        print(
            "Incident type   :",
            repr(getattr(self.incident, "bug_type", None))
        )
        print(
            "Incident PID    :",
            repr(getattr(self.incident, "pid", None))
        )
        print("=" * 70)

        try:

            reproducer = FailureReproducer(
                incident=self.incident,
                source_context=source_context,
                evidence_text=evidence_text,
                device_serial=device_serial,
                minimum_confidence=0.70,
                observation_seconds=observation_seconds,
            )

        except Exception as exc:

            print()
            print(
                "❌ Failed to create "
                "FailureReproducer."
            )
            print(
                "Reason:",
                exc,
            )
            return False

        # ----------------------------------------------------
        # Execute generic reproduction
        # ----------------------------------------------------
        try:

            result = reproducer.reproduce()

        except Exception as exc:

            print()
            print(
                "❌ Generic failure reproduction "
                "failed unexpectedly."
            )

            print(
                "Error:",
                exc,
            )

            return False

        if result is None:

            print()
            print(
                "❌ FailureReproducer returned "
                "no result."
            )

            return False

        # ----------------------------------------------------
        # Print final verification summary
        # ----------------------------------------------------

        print()
        print(
            "========== VERIFICATION RESULT =========="
        )

        print(
            "Failure Type      :",
            failure_type,
        )

        print(
            "Package           :",
            package,
        )

        print(
            "Action Found      :",
            result.action_found,
        )

        print(
            "Action Executed   :",
            result.action_executed,
        )

        print(
            "Confidence        :",
            f"{result.confidence:.2f}",
        )

        print(
            "Process Alive     :",
            result.process_alive,
        )

        print(
            "Failure Reproduced:",
            result.failure_reproduced,
        )

        print(
            "Reason            :",
            result.reason,
        )

        print(
            "=========================================="
        )

        # ----------------------------------------------------
        # Verification decision
        # ----------------------------------------------------

        if not result.success:

            print()
            print(
                "❌ Generic failure reproduction "
                "failed."
            )

            return False

        if result.failure_reproduced:

            print()
            print(
                "❌ ORIGINAL FAILURE STILL EXISTS."
            )

            return False

        if not result.process_alive:

            print()
            print(
                "⚠️ APPLICATION PROCESS IS NOT ALIVE."
            )

            print(
                "Process state is diagnostic only; "
                "it is not used as the verification decision."
            )

        print()
        print(
            "✅ ORIGINAL FAILURE NOT REPRODUCED."
        )

        print(
            "✅ PATCHED APPLICATION VERIFIED."
        )

        return True



    def apply_ai_patch(self):

        if not self.patch:

            print()
            print(
                "❌ Cannot apply: patch object is missing."
            )

            return False

        if not self.patch_validation:

            print()
            print(
                "❌ Cannot apply: patch was not validated."
            )

            return False

        if not bool(self.patch_validation):

            print()
            print(
                "❌ Cannot apply: PatchValidator rejected patch."
            )

            return False

        if not self.source:

            print()
            print(
                "❌ Cannot apply: source file is missing."
            )

            return False

        source_path = (
            self.source.get(
                "path",
                "",
            )
        )

        old_code = getattr(
            self.patch,
            "old_code",
            "",
        )

        new_code = getattr(
            self.patch,
            "new_code",
            "",
        )

        if not old_code.strip():

            print()
            print(
                "❌ Cannot apply: old_code is empty."
            )

            return False

        if not new_code.strip():

            print()
            print(
                "❌ Cannot apply: new_code is empty."
            )

            return False

        print()
        print(
            "→ Applying validated patch..."
        )

        print(
            "  Source:",
            source_path
        )

        print(
            "  old_code length:",
            len(old_code)
        )

        print(
            "  new_code length:",
            len(new_code)
        )

        try:

            result = self.patch_applier.apply(
                source_path=source_path,
                old_code=old_code,
                new_code=new_code,
            )

        except Exception as exc:

            print()
            print(
                "❌ PatchApplier failed unexpectedly:"
            )

            print(exc)

            return False

        print(result)

        if not result.success:

            print()
            print(
                "❌ Patch was NOT applied."
            )

            return False

        # --------------------------------------------------------
        # Keep the complete PatchApplicationResult.
        #
        # Step 9 uses the backup path if the build fails.
        # --------------------------------------------------------

        self.patch_application = result

        print()
        print(
            "✅ Patch application verified."
        )

        print(
            "  Backup:",
            result.backup_path
        )

        return True


    # ============================================================
    # PATCH VALIDATION
    # ============================================================

    def validate_ai_patch(self):

        if not self.patch:

            print()
            print(
                "❌ Cannot validate: patch object is missing."
            )

            return False

        if not self.source:

            print()
            print(
                "❌ Cannot validate: source file is missing."
            )

            return False

        source_path = (
            self.source.get(
                "path",
                "",
            )
        )

        failure_type = (
            self.analysis.failure_type
            if self.analysis
            else getattr(
                self.incident,
                "bug_type",
                "UNKNOWN",
            )
        )

        print()
        print(
            "→ Validating generated patch..."
        )

        print(
            "  Source:",
            source_path
        )

        print(
            "  Failure type:",
            failure_type
        )

        try:

            self.patch_validation = (
                self.patch_validator.validate(
                    patch=self.patch,
                    source_path=source_path,
                    failure_type=failure_type,
                )
            )

        except Exception as exc:

            print()
            print(
                "❌ Patch validation failed unexpectedly:"
            )

            print(exc)

            self.patch_validation = None

            return False

        print(
            self.patch_validation
        )

        return bool(
            self.patch_validation
        )

    # ============================================================
    # PIPELINE STATUS
    # ============================================================

    def print_pipeline_status(
        self,
        patch_generated=False,
        patch_valid=False,
        patch_applied=False,
        build_success=None,
        install_success=None,
        launch_success=None,
        tests_success=None,
        verification_status="NOT RUN",
        rollback_status="NOT REQUIRED",
    ):

        print()
        print("=" * 70)
        print("             VAMP PIPELINE STATUS")
        print("=" * 70)

        print(
            "Diagnosis     : COMPLETE"
        )

        print(
            "AI Analysis   : COMPLETE"
        )

        print(
            "Patch Proposal:",
            "GENERATED"
            if patch_generated
            else "NOT GENERATED"
        )

        if patch_generated:

            print(
                "Patch Valid   :",
                "ACCEPTED"
                if patch_valid
                else "REJECTED"
            )

        else:

            print(
                "Patch Valid   : NOT CHECKED"
            )

        if patch_applied:

            print(
                "Patch Applied : SUCCESS"
            )

        elif patch_valid:

            print(
                "Patch Applied : FAILED"
            )

        else:

            print(
                "Patch Applied : NOT YET"
            )

        if build_success is None:
            print(
                "Build         : NOT YET"
            )
        else:
            print(
                "Build         :",
                "SUCCESS"
                if build_success
                else "FAILED"
            )

        if install_success is None:
            print(
                "Install       : NOT YET"
            )
        else:
            print(
                "Install       :",
                "SUCCESS"
                if install_success
                else "FAILED"
            )

        if launch_success is None:
            print(
                "Launch        : NOT YET"
            )
        else:
            print(
                "Launch        :",
                "SUCCESS"
                if launch_success
                else "FAILED"
            )

        if tests_success is None:
            print(
                "Tests         : NOT YET"
            )
        else:
            print(
                "Tests         :",
                "PASSED"
                if tests_success
                else "FAILED"
            )

        print(
            "Verification  :",
            verification_status
        )

        print(
            "Rollback      :",
            rollback_status
        )

        print("=" * 70)

    # ============================================================
    # CORRECT ANALYSIS FROM INCIDENT
    # ============================================================

    def correct_analysis_from_incident(self):

        if not self.analysis:
            return

        incident_reason = (
            getattr(
                self.incident,
                "reason",
                "",
            )
            or ""
        ).strip()

        incident_type = (
            getattr(
                self.incident,
                "bug_type",
                "",
            )
            or ""
        ).upper()

        if incident_type == "ANR":

            if incident_reason:

                current_reason = (
                    self.analysis.anr_reason
                    or ""
                ).strip()

                suspicious_reason = (
                    not current_reason
                    or current_reason.lower()
                    in {
                        "system compaction memory stats",
                        "unknown",
                    }
                    or "compaction memory"
                    in current_reason.lower()
                )

                if suspicious_reason:

                    print()
                    print(
                        "⚠ Correcting unreliable ANR reason "
                        "from Incident."
                    )

                    print(
                        "Collected:",
                        current_reason
                        or "<empty>"
                    )

                    print(
                        "Incident :",
                        incident_reason
                    )

                    self.analysis.anr_reason = (
                        incident_reason
                    )

    # ============================================================
    # PROJECT RESOLUTION
    # ============================================================

    def resolve_project(self, package):

        return self.resolver.resolve(
            package
        )

    # ============================================================
    # SOURCE LOCATION
    # ============================================================

    def locate_source(self):

        workspace = Path(
            self.workspace
        ).resolve()

        report = (
            self.build_source_report()
        )

        # --------------------------------------------------------
        # NATIVE CRASH SOURCE RESOLUTION
        #
        # Framework/Launcher3/native-runtime frames are evidence,
        # not application source locations.
        #
        # Resolve:
        #
        #   Application Activity
        #          ↓
        #   external JNI method
        #          ↓
        #   JNI symbol
        #          ↓
        #   C/C++ implementation
        # --------------------------------------------------------

        if report.get("type") == "NATIVE_CRASH":

            activity = (
                self.analysis.activity
                if self.analysis
                else ""
            )

            activity_class = (
                self.extract_activity_class(
                    activity
                )
            )

            native_report = dict(
                report
            )

            if activity_class:

                native_report["class"] = (
                    activity_class
                )

            print()
            print(
                "→ Native crash source resolution"
            )

            print(
                "  Application :",
                native_report.get(
                    "package"
                )
                or "<unknown>",
            )

            print(
                "  Activity    :",
                activity_class
                or "<unknown>",
            )

            print(
                "  Framework frames are evidence only."
            )

            native_source = (
                find_native_source(
                    workspace,
                    native_report,
                )
            )

            if native_source:

                print(
                    "  Native Source:",
                    native_source.get(
                        "path"
                    ),
                )

                return native_source

            print(
                "  Native source could not be "
                "resolved from JNI symbols."
            )

        # --------------------------------------------------------
        # FIRST PRIORITY:
        # Exact application source frame from failure evidence.
        #
        # Example:
        #   com.example.displaycrashapp.CrashRenderer
        #   CrashRenderer.kt:90
        #
        # This is the most reliable source location because it
        # comes directly from the actual failure stack trace.
        # --------------------------------------------------------

        if self.analysis:

            source_frames = (
                self.analysis.source_frames
                or []
            )

            for frame in source_frames:

                if not isinstance(
                    frame,
                    dict
                ):
                    continue

                filename = (
                    frame.get(
                        "file",
                        ""
                    )
                    or ""
                )

                class_name = (
                    frame.get(
                        "class",
                        ""
                    )
                    or ""
                )

                if not filename:
                    continue

                print()
                print(
                    "→ Searching exact failure source:"
                )

                print(
                    "  Class :",
                    class_name or "<unknown>"
                )

                print(
                    "  File  :",
                    filename
                )

                print(
                    "  Line  :",
                    frame.get(
                        "line"
                    )
                )

                candidates = list(
                    workspace.rglob(
                        filename
                    )
                )

                candidates = [
                    path
                    for path in candidates
                    if self.is_application_source(
                        path
                    )
                ]

                if class_name:

                    simple_class = (
                        class_name
                        .split(".")[-1]
                    )

                    class_candidates = [
                        path
                        for path in candidates
                        if path.stem == simple_class
                    ]

                    if class_candidates:
                        candidates = (
                            class_candidates
                        )

                if candidates:

                    best = (
                        self.select_best_candidate(
                            candidates
                        )
                    )

                    print(
                        "  Source:",
                        best
                    )

                    return self.source_from_path(
                        best
                    )

        # --------------------------------------------------------
        # SECOND PRIORITY:
        # Existing stack-trace source search.
        #
        # This preserves the existing generic source-resolution
        # behavior for crashes/ANRs where source-frame discovery
        # above does not resolve a file.
        # --------------------------------------------------------

        source = find_source(
            workspace,
            report
        )

        if source:

            return source

        # --------------------------------------------------------
        # THIRD PRIORITY:
        # Activity-based discovery.
        #
        # This remains a fallback only. It must never override a
        # valid failure stack frame.
        # --------------------------------------------------------

        activity = (
            self.analysis.activity
            if self.analysis
            else ""
        )

        activity_class = (
            self.extract_activity_class(
                activity
            )
        )

        if activity_class:

            print()
            print(
                "→ Searching by Activity class:"
            )

            print(
                activity_class
            )

            candidates = []

            candidates.extend(
                workspace.rglob(
                    f"{activity_class.split('.')[-1]}.kt"
                )
            )

            candidates.extend(
                workspace.rglob(
                    f"{activity_class.split('.')[-1]}.java"
                )
            )

            candidates = [
                path
                for path in candidates
                if self.is_application_source(
                    path
                )
            ]

            if candidates:

                best = (
                    self.select_best_candidate(
                        candidates
                    )
                )

                return self.source_from_path(
                    best
                )

        # --------------------------------------------------------
        # FOURTH PRIORITY:
        # Package source directory.
        # --------------------------------------------------------

        package = (
            self.analysis.package
            if self.analysis
            else getattr(
                self.incident,
                "package",
                "",
            )
        )

        if package:

            package_path = (
                package.replace(
                    ".",
                    "/"
                )
            )

            search_paths = [
                workspace
                / "app"
                / "src"
                / "main"
                / "java"
                / package_path,

                workspace
                / "app"
                / "src"
                / "main"
                / "kotlin"
                / package_path,

                workspace
                / "src"
                / "main"
                / "java"
                / package_path,

                workspace
                / "src"
                / "main"
                / "kotlin"
                / package_path,
            ]

            candidates = []

            for directory in search_paths:

                if not directory.exists():
                    continue

                candidates.extend(
                    directory.rglob(
                        "*.kt"
                    )
                )

                candidates.extend(
                    directory.rglob(
                        "*.java"
                    )
                )

            candidates = [
                path
                for path in candidates
                if self.is_application_source(
                    path
                )
            ]

            if candidates:

                best = (
                    self.select_best_candidate(
                        candidates
                    )
                )

                print()
                print(
                    "→ Package source candidate:"
                )

                print(
                    best
                )

                return self.source_from_path(
                    best
                )

        return None

    # ============================================================
    # BUILD SOURCE REPORT
    # ============================================================

    def build_source_report(self):

        analysis = self.analysis

        failure_type = (
            analysis.failure_type
            if analysis
            else getattr(
                self.incident,
                "bug_type",
                "UNKNOWN",
            )
        )

        package = (
            analysis.package
            if analysis
            else getattr(
                self.incident,
                "package",
                "",
            )
        )

        report = {
            "package": package or "",
            "class": "",
            "method": "",
            "file": "",
            "line": None,
            "exception": (
                analysis.exception
                if analysis
                else ""
            ),
            "reason": (
                analysis.anr_reason
                if analysis
                else getattr(
                    self.incident,
                    "reason",
                    "",
                )
            ),
            "type": failure_type,
            "stacktrace": "",
        }

        # --------------------------------------------------------
        # NATIVE CRASH
        #
        # Native stack frames can contain Android framework,
        # Launcher3, runtime, or other non-application frames.
        #
        # Therefore the Activity is used as the starting point
        # for JNI/native source discovery.
        # --------------------------------------------------------

        if failure_type == "NATIVE_CRASH":

            activity = (
                analysis.activity
                if analysis
                else ""
            )

            activity_class = (
                self.extract_activity_class(
                    activity
                )
            )

            if activity_class:
                report["class"] = activity_class

            return report

        # --------------------------------------------------------
        # JAVA / KOTLIN / ANR / OTHER FAILURE
        #
        # Preserve the existing source-frame behavior.
        # --------------------------------------------------------

        if analysis:

            frames = (
                analysis.source_frames
                or []
            )

            if frames:

                frame = frames[0]

                if isinstance(
                    frame,
                    dict
                ):

                    report["class"] = (
                        frame.get(
                            "class",
                            ""
                        )
                    )

                    report["method"] = (
                        frame.get(
                            "method",
                            ""
                        )
                    )

                    report["file"] = (
                        frame.get(
                            "file",
                            ""
                        )
                    )

                    report["line"] = (
                        frame.get(
                            "line"
                        )
                    )

        return report

    def build_llm_input(self):

        analysis = self.analysis

        # --------------------------------------------------------
        # Failure information
        # --------------------------------------------------------

        log_data = {
            "type": (
                analysis.failure_type
                if analysis
                else getattr(
                    self.incident,
                    "bug_type",
                    "UNKNOWN",
                )
            ),

            "bug_type": (
                analysis.failure_type
                if analysis
                else getattr(
                    self.incident,
                    "bug_type",
                    "UNKNOWN",
                )
            ),

            "package": (
                analysis.package
                if analysis
                else getattr(
                    self.incident,
                    "package",
                    "",
                )
            ),

            "process": (
                analysis.process
                if analysis
                else getattr(
                    self.incident,
                    "process",
                    "",
                )
            ),

            "pid": (
                analysis.pid
                if analysis
                else getattr(
                    self.incident,
                    "pid",
                    None,
                )
            ),

            "activity": (
                analysis.activity
                if analysis
                else ""
            ),

            "exception": (
                analysis.exception
                if analysis
                else getattr(
                    self.incident,
                    "exception",
                    "",
                )
            ),

            "reason": (
                analysis.anr_reason
                if analysis
                else getattr(
                    self.incident,
                    "reason",
                    "",
                )
            ),

            "thread": (
                getattr(
                    analysis,
                    "thread",
                    None,
                )
                or getattr(
                    self.incident,
                    "thread",
                    "",
                )
                or ""
            ),

            "stacktrace": (
                getattr(
                    self.incident,
                    "stack_trace",
                    "",
                )
                or ""
            ),

            "indicators": (
                ", ".join(
                    analysis.indicators
                )
                if analysis
                and isinstance(
                    getattr(
                        analysis,
                        "indicators",
                        None,
                    ),
                    list
                )
                else (
                    getattr(
                        analysis,
                        "indicators",
                        "",
                    )
                    if analysis
                    else ""
                )
            ),

            "confidence": (
                analysis.confidence
                if analysis
                else "UNKNOWN"
            ),
        }

        # --------------------------------------------------------
        # Source information
        # --------------------------------------------------------

        source_file = (
            self.source.get(
                "filename",
                "",
            )
            if self.source
            else ""
        )

        source_path = (
            self.source.get(
                "path",
                "",
            )
            if self.source
            else ""
        )

        source_snippet = ""

        source_code = ""

        if self.context:

            source_snippet = (
                self.context.get(
                    "snippet",
                    "",
                )
                or self.context.get(
                    "source",
                    "",
                )
                or self.context.get(
                    "content",
                    "",
                )
                or ""
            )

            source_code = (
                self.context.get(
                    "source",
                    "",
                )
                or self.context.get(
                    "content",
                    "",
                )
                or ""
            )

            if not source_code:

                source_code = (
                    self.context.get(
                        "code",
                        "",
                    )
                    or ""
                )

        source_data = {
            "file": source_file,

            "filename": source_file,

            "path": source_path,

            "snippet": source_snippet,

            "code": source_code,
        }

        return {
            "log": log_data,
            "source": source_data,
        }

    # ============================================================
    # AI ANALYSIS
    # ============================================================

    def generate_ai_analysis(self):

        llm_input = (
            self.build_llm_input()
        )

        print()
        print("[6] AI diagnosis and patch...")

        patch = ask_llm(
            llm_input
        )

        return patch

    # ============================================================
    # AI RESULT PRINT
    # ============================================================

    def print_ai_result(self):

        if not self.patch:
            return

        print("✓ AI analysis completed")

        if self.patch.has_patch():
            print("✓ Patch generated")
        else:
            print("✓ No source patch required")

    # ============================================================
    # ACTIVITY CLASS EXTRACTION
    # ============================================================

    @staticmethod
    def extract_activity_class(
        activity
    ):

        if not activity:
            return ""

        value = activity.strip()

        if "/" not in value:
            return ""

        package, component = (
            value.split(
                "/",
                1
            )
        )

        package = package.strip()
        component = component.strip()

        if not component:
            return ""

        if component.startswith("."):

            return (
                package
                + component
            )

        if component.startswith(
            package + "."
        ):

            return component

        return component

    # ============================================================
    # SOURCE FILTERING
    # ============================================================

    @staticmethod
    def is_application_source(
        path
    ):

        path = Path(path)

        if path.suffix not in (
            ".kt",
            ".java",
        ):
            return False

        path_text = str(path)

        if "/build/" in path_text:
            return False

        if "/generated/" in path_text:
            return False

        if "/test/" in path_text:
            return False

        if "/androidTest/" in path_text:
            return False

        return (
            "/src/main/" in path_text
        )

    # ============================================================
    # SOURCE CANDIDATE SCORING
    # ============================================================

    def select_best_candidate(
        self,
        candidates,
    ):

        package = (
            self.analysis.package
            if self.analysis
            else ""
        )

        package_path = (
            package.replace(
                ".",
                "/"
            )
            if package
            else ""
        )

        activity = (
            self.analysis.activity
            if self.analysis
            else ""
        )

        activity_class = (
            self.extract_activity_class(
                activity
            )
        )

        activity_name = (
            activity_class.split(
                "."
            )[-1]
            if activity_class
            else ""
        )

        scored = []

        for path in candidates:

            score = 0

            path_text = str(path)

            if "/src/main/" in path_text:
                score += 20

            if (
                package_path
                and package_path in path_text
            ):
                score += 60

            if (
                activity_name
                and path.stem
                == activity_name
            ):
                score += 100

            if path.suffix in (
                ".kt",
                ".java",
            ):
                score += 10

            scored.append(
                (
                    score,
                    path
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                str(item[1])
            ),
            reverse=True
        )

        return scored[0][1]

    # ============================================================
    # SOURCE OBJECT
    # ============================================================

    def source_from_path(
        self,
        path
    ):

        path = Path(
            path
        ).resolve()

        return {
            "path": str(path),

            "filename": path.name,

            "directory": str(
                path.parent
            ),

            "package": (
                self.analysis.package
                if self.analysis
                else ""
            ),

            "class": path.stem,

            "workspace": str(
                Path(
                    self.workspace
                ).resolve()
            ),
        }

    # ============================================================
    # SOURCE CONTEXT
    # ============================================================

    def read_source_context(self):

        error_line = None
        method = None

        if self.analysis:

            frames = (
                self.analysis.source_frames
                or []
            )

            if frames:

                frame = frames[0]

                if isinstance(
                    frame,
                    dict
                ):

                    error_line = (
                        frame.get(
                            "line"
                        )
                    )

                    method = (
                        frame.get(
                            "method"
                        )
                    )

        return read_context(
            self.source["path"],
            error_line=error_line,
            method=method,
        )

    # ============================================================
    # INCIDENT PRINT
    # ============================================================

    def print_incident(self):

        print()
        print(
            "Incident Type :",
            getattr(
                self.incident,
                "bug_type",
                "UNKNOWN",
            ),
        )

        print(
            "Package       :",
            getattr(
                self.incident,
                "package",
                "",
            )
            or "<unknown>",
        )

        print(
            "Process       :",
            getattr(
                self.incident,
                "process",
                "",
            )
            or "<unknown>",
        )

        print(
            "PID           :",
            getattr(
                self.incident,
                "pid",
                None,
            )
            or "<unknown>",
        )

        print(
            "Reason        :",
            getattr(
                self.incident,
                "reason",
                "",
            )
            or "<unknown>",
        )

        print(
            "Exception     :",
            getattr(
                self.incident,
                "exception",
                "",
            )
            or "<unknown>",
        )

    # ============================================================
    # FINAL DIAGNOSIS
    # ============================================================

    def print_final_diagnosis(
        self,
        source_found=False,
        context_loaded=False,
    ):

        print()
        print("=" * 70)
        print("               VAMP DIAGNOSIS")
        print("=" * 70)

        if self.analysis:

            print(
                "Failure Type :",
                self.analysis.failure_type
            )

            print(
                "Package      :",
                self.analysis.package
                or "<unknown>"
            )

            print(
                "Process      :",
                self.analysis.process
                or "<unknown>"
            )

            print(
                "PID          :",
                self.analysis.pid
                or "<unknown>"
            )

            if self.analysis.activity:

                print(
                    "Activity     :",
                    self.analysis.activity
                )

            if self.analysis.exception:

                print(
                    "Exception    :",
                    self.analysis.exception
                )

            if self.analysis.exception_message:

                print(
                    "Message      :",
                    self.analysis.exception_message
                )

            if self.analysis.anr_reason:

                print(
                    "ANR Reason   :",
                    self.analysis.anr_reason
                )

            if self.analysis.native_signal:

                signal_text = (
                    self.analysis.native_signal
                )

                if self.analysis.native_signal_name:

                    signal_text += (
                        " ("
                        + self.analysis.native_signal_name
                        + ")"
                    )

                print(
                    "Native Signal:",
                    signal_text
                )

            print(
                "Likely Area  :",
                self.analysis.likely_area
            )

            print(
                "Likely Cause :",
                self.analysis.likely_cause
            )

            print(
                "Confidence   :",
                self.analysis.confidence
            )

        print()

        print(
            "Workspace    :",
            self.workspace
            or "<not resolved>"
        )

        print(
            "Source Found :",
            "YES"
            if source_found
            else "NO"
        )

        if self.source:

            print(
                "Source File  :",
                self.source["path"]
            )

        print(
            "Context      :",
            "LOADED"
            if context_loaded
            else "NOT LOADED"
        )

        print("=" * 70)


# ================================================================
# MANUAL TEST
# ================================================================

if __name__ == "__main__":

    from modules.models import Incident

    incident = Incident(
        timestamp="",
        device_serial="0.0.0.0:6520",
        package="com.example.demo",
        process="com.example.demo",
        pid=5479,
        bug_type="ANR",
        exception="",
        reason="Input dispatching timed out",
        thread="",
        stack_trace="",
        raw_log="",
    )

    agent = BugFixAgent(
        incident=incident
    )

    result = agent.run()

    print()
    print(
        "Diagnosis result:",
        result
    )
