"""Unit tests for the Python-backed orchestration helpers."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from typing import cast
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sst_container_factory import adapters, build_spec, cli, github_actions, logging_utils, orchestration


class OrchestrationTests(unittest.TestCase):
    """Validate the Python orchestration transition layer."""

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the repository root once for the Python test suite."""

        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.host_platform = orchestration.detect_host_platform()
        cls.host_arch = orchestration.platform_to_arch(cls.host_platform)

    def _run_python_cli(
        self,
        argv: list[str],
        *,
        env_updates: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run the Python CLI entrypoint and capture stdout and stderr."""

        output = io.StringIO()
        errors = io.StringIO()
        with patch.dict(os.environ, env_updates or {}, clear=False):
            with redirect_stdout(output), redirect_stderr(errors):
                status = cli.main(argv)
        return status, output.getvalue(), errors.getvalue()

    def _run_shell_wrapper(
        self,
        relative_path: str,
        argv: list[str],
        *,
        env_updates: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run a shell wrapper through bash and capture stdout and stderr."""

        env = os.environ.copy()
        env["PYTHON_BIN"] = sys.executable
        if env_updates:
            env.update(env_updates)

        result = subprocess.run(
            ["bash", str(self.repo_root / relative_path), *argv],
            cwd=self.repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr

    def _get_non_host_platform(self) -> str:
        """Return a single non-host Linux platform for validation tests."""

        if self.host_platform == "linux/amd64":
            return "linux/arm64"
        return "linux/amd64"

    def test_download_sources_downloads_requested_artifacts(self) -> None:
        """The Python downloader should fetch the requested tarballs into a target directory."""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            destination = temp_path / "downloads"
            destination.mkdir()

            mpich_source = temp_path / "mpich-source.tar.gz"
            core_source = temp_path / "sstcore-source.tar.gz"
            elements_source = temp_path / "sstelements-source.tar.gz"
            mpich_source.write_bytes(b"mpich-source")
            core_source.write_bytes(b"sst-core-source")
            elements_source.write_bytes(b"sst-elements-source")

            env = {
                "SST_DOWNLOAD_MPICH_URL": mpich_source.resolve().as_uri(),
                "SST_DOWNLOAD_CORE_URL": core_source.resolve().as_uri(),
                "SST_DOWNLOAD_ELEMENTS_URL": elements_source.resolve().as_uri(),
            }
            with patch.dict(os.environ, env, clear=False):
                result = orchestration.download_sources(
                    sst_version="15.1.2",
                    sst_elements_version="15.1.0",
                    mpich_version="4.0.2",
                    download_mpich=True,
                    download_sst_core=True,
                    download_sst_elements=True,
                    force_mode=True,
                    destination_dir=destination,
                )

            self.assertEqual(
                result.requested_files,
                (
                    "mpich-4.0.2.tar.gz",
                    "sstcore-15.1.2.tar.gz",
                    "sstelements-15.1.0.tar.gz",
                ),
            )
            self.assertEqual((destination / "mpich-4.0.2.tar.gz").read_bytes(), b"mpich-source")
            self.assertEqual((destination / "sstcore-15.1.2.tar.gz").read_bytes(), b"sst-core-source")
            self.assertEqual(
                (destination / "sstelements-15.1.0.tar.gz").read_bytes(),
                b"sst-elements-source",
            )

    def test_cli_download_sources_maps_explicit_selection(self) -> None:
        """The Python CLI should translate downloader options into explicit request flags."""

        with patch.object(cli, "download_sources") as download_sources:
            status = cli.main(
                [
                    "download-sources",
                    "--sst-version",
                    "15.1.2",
                    "--sst-elements-version",
                    "15.1.0",
                    "--force",
                ]
            )

        self.assertEqual(status, 0)
        download_sources.assert_called_once_with(
            sst_version="15.1.2",
            sst_elements_version="15.1.0",
            mpich_version=orchestration.DEFAULT_MPICH_VERSION,
            download_mpich=False,
            download_sst_core=True,
            download_sst_elements=True,
            force_mode=True,
        )

    def test_cli_build_experiment_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit build experiment arguments."""

        with patch.object(cli, "build") as build_api:
            status = cli.main(
                [
                    "build",
                    "experiment",
                    "--base-image",
                    "sst-core:latest",
                    "--platform",
                    self.host_platform,
                    "--validation",
                    "metadata",
                    "--engine",
                    "docker",
                    "--experiment-name",
                    "phold-example",
                ]
            )

        self.assertEqual(status, 0)
        request = build_api.call_args.args[0]
        self.assertIsInstance(request, orchestration.BuildRequest)
        self.assertEqual(request.container_type, "experiment")
        self.assertEqual(request.experiment_name, "phold-example")
        self.assertEqual(request.target_platform, self.host_platform)
        self.assertEqual(request.base_image, "sst-core:latest")
        self.assertEqual(request.validation_mode, "metadata")
        self.assertEqual(request.container_engine, "docker")

    def test_cli_build_source_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit build source arguments."""

        with patch.object(cli, "build") as build_api:
            status = cli.main(
                [
                    "build",
                    "source",
                    "--core-ref",
                    "main",
                    "--platform",
                    self.host_platform,
                    "--tag-suffix",
                    "demo",
                    "--validation",
                    "metadata",
                    "--engine",
                    "docker",
                    "--enable-perf-tracking",
                ]
            )

        self.assertEqual(status, 0)
        request = build_api.call_args.args[0]
        self.assertIsInstance(request, orchestration.BuildRequest)
        self.assertEqual(request.container_type, "custom")
        self.assertEqual(request.sst_core_ref, "main")
        self.assertEqual(request.target_platform, self.host_platform)
        self.assertEqual(request.tag_suffix, "demo")
        self.assertEqual(request.validation_mode, "metadata")
        self.assertTrue(request.enable_perf_tracking)
        self.assertEqual(request.container_engine, "docker")

    def test_cli_build_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit build arguments."""

        with patch.object(cli, "build") as build_api:
            status = cli.main(
                [
                    "build",
                    "core",
                    "--sst-version",
                    "15.1.2",
                    "--platform",
                    self.host_platform,
                    "--tag-suffix",
                    "demo",
                    "--validation",
                    "metadata",
                    "--engine",
                    "docker",
                    "--cleanup",
                ]
            )

        self.assertEqual(status, 0)
        request = build_api.call_args.args[0]
        self.assertIsInstance(request, orchestration.BuildRequest)
        self.assertEqual(request.container_type, "core")
        self.assertEqual(request.target_platform, self.host_platform)
        self.assertEqual(request.sst_version, "15.1.2")
        self.assertEqual(request.tag_suffix, "demo")
        self.assertTrue(request.tag_suffix_set)
        self.assertEqual(request.validation_mode, "metadata")
        self.assertTrue(request.cleanup)
        self.assertEqual(request.container_engine, "docker")

    def test_cli_build_source_rejects_mutually_exclusive_core_source_flags(self) -> None:
        """The Python CLI should let argparse enforce source input mutual exclusion."""

        status, _stdout, stderr = self._run_python_cli(
            [
                "build",
                "source",
                "--core-path",
                "/tmp/sst-core",
                "--core-ref",
                "main",
            ]
        )

        self.assertEqual(status, 1)
        self.assertIn("not allowed with argument --core-path", stderr)

    def test_cli_build_experiment_rejects_invalid_validation_mode(self) -> None:
        """The Python CLI should let argparse choices enforce build experiment validation modes."""

        status, _stdout, stderr = self._run_python_cli(
            [
                "build",
                "experiment",
                "--validation",
                "no-exec",
                "--experiment-name",
                "phold-example",
            ]
        )

        self.assertEqual(status, 1)
        self.assertIn("invalid choice: 'no-exec'", stderr)

    def test_cli_build_experiment_requires_experiment_name(self) -> None:
        """The build experiment parser should require the experiment-name option."""

        status, _stdout, stderr = self._run_python_cli(["build", "experiment"])

        self.assertEqual(status, 1)
        self.assertIn("the following arguments are required: --experiment-name", stderr)

    def test_cli_build_rejects_invalid_container_type(self) -> None:
        """The Python CLI should let argparse enforce build container choices."""

        status, _stdout, stderr = self._run_python_cli(["build", "not-a-type"])

        self.assertEqual(status, 1)
        self.assertIn("argument CONTAINER_TYPE: invalid choice: 'not-a-type'", stderr)

    def test_cli_build_dev_rejects_perf_tracking_flag(self) -> None:
        """The dev build subparser should reject perf tracking at parse time."""

        status, _stdout, stderr = self._run_python_cli(
            ["build", "dev", "--enable-perf-tracking"]
        )

        self.assertEqual(status, 1)
        self.assertIn("unrecognized arguments: --enable-perf-tracking", stderr)

    def test_cli_build_source_help_documents_local_checkout_option(self) -> None:
        """Build source help should advertise local checkout support."""

        status, stdout, _stderr = self._run_python_cli(["build", "source", "--help"])

        self.assertEqual(status, 0)
        self.assertIn("--core-path PATH", stdout)
        self.assertNotIn("--sst-core-ref", stdout)

    def test_cli_download_sources_help_documents_elements_version(self) -> None:
        """Downloader help should include the SST-elements version option."""

        status, stdout, _stderr = self._run_python_cli(["download-sources", "--help"])

        self.assertEqual(status, 0)
        self.assertIn("--sst-elements-version", stdout)

    def test_cli_build_experiment_help_omits_removed_prefix_option(self) -> None:
        """Build experiment help should not expose the retired prefix option."""

        status, stdout, _stderr = self._run_python_cli(["build", "experiment", "--help"])

        self.assertEqual(status, 0)
        self.assertNotIn("--prefix", stdout)

    def test_cli_build_help_lists_source_subcommand(self) -> None:
        """Build help should list the source subcommand and omit legacy engine aliases."""

        status, stdout, _stderr = self._run_python_cli(["build", "--help"])

        self.assertEqual(status, 0)
        self.assertIn("source", stdout)
        self.assertIn("Build from a local checkout or selected repository/ref", stdout)
        self.assertNotIn("--docker", stdout)

    def test_cli_build_source_help_documents_perf_tracking(self) -> None:
        """The build source subcommand help should retain its perf flag."""

        status, stdout, _stderr = self._run_python_cli(["build", "source", "--help"])

        self.assertEqual(status, 0)
        self.assertIn("--enable-perf-tracking", stdout)

    def test_cli_build_experiment_help_omits_perf_tracking(self) -> None:
        """The build experiment subcommand should not advertise perf tracking."""

        status, stdout, _stderr = self._run_python_cli(["build", "experiment", "--help"])

        self.assertEqual(status, 0)
        self.assertNotIn("--enable-perf-tracking", stdout)

    def test_shell_build_wrapper_help_lists_source_subcommand(self) -> None:
        """The canonical build wrapper should expose the expected top-level help surface."""

        status, stdout, stderr = self._run_shell_wrapper("sst_container_factory/bin/build.sh", ["--help"])

        self.assertEqual(status, 0, stderr)
        self.assertIn("source      Build from a local checkout or selected repository/ref", stdout)
        self.assertNotIn("--docker", stdout)
        self.assertNotIn("--validate ", stdout)

    def test_shell_build_source_wrapper_help_documents_checkout_and_perf(self) -> None:
        """The source build wrapper help should expose source-specific options."""

        status, stdout, stderr = self._run_shell_wrapper(
            "sst_container_factory/bin/build.sh",
            ["source", "--help"],
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("--core-path PATH", stdout)
        self.assertIn("--enable-perf-tracking", stdout)
        self.assertNotIn("--sst-core-ref", stdout)

    def test_shell_build_wrapper_rejects_invalid_arguments(self) -> None:
        """The canonical build wrapper should preserve parser-level contract failures."""

        scenarios = [
            (
                ["core", "--platforms", "linux/amd64"],
                "unrecognized arguments: --platforms",
            ),
            (
                ["dev", "--enable-perf-tracking"],
                "unrecognized arguments: --enable-perf-tracking",
            ),
            (
                ["core", "--validate-only", "--validation", "none"],
                "--validate-only requires a validation mode other than none",
            ),
            (
                ["not-a-type"],
                "invalid choice: 'not-a-type'",
            ),
        ]

        for argv, expected_error in scenarios:
            with self.subTest(argv=argv):
                status, stdout, stderr = self._run_shell_wrapper("sst_container_factory/bin/build.sh", argv)
                combined_output = stdout + stderr
                self.assertEqual(status, 1)
                self.assertIn(expected_error, combined_output)

    def test_shell_build_wrapper_rejects_non_host_platform(self) -> None:
        """The canonical build wrapper should keep host-platform enforcement."""

        status, stdout, stderr = self._run_shell_wrapper(
            "sst_container_factory/bin/build.sh",
            ["core", "--platform", self._get_non_host_platform()],
        )

        self.assertEqual(status, 1)
        self.assertIn("Cross-platform builds are not supported by this script", stdout + stderr)

    def test_shell_download_wrapper_help_documents_elements_version(self) -> None:
        """The tarball download wrapper should expose the SST-elements version option."""

        status, stdout, stderr = self._run_shell_wrapper(
            "sst_container_factory/bin/download-sources.sh",
            ["--help"],
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("--sst-elements-version", stdout)

    def test_removed_workflow_helper_commands_are_rejected(self) -> None:
        """Dead workflow-only helper commands should stay out of the public CLI."""

        for command in (
            "workflow-prepare-image-config",
            "workflow-validate-source-inputs",
            "workflow-validate-experiment-inputs",
        ):
            with self.subTest(command=command):
                status, _stdout, stderr = self._run_python_cli([command])

                self.assertEqual(status, 1)
                self.assertIn(f"invalid choice: '{command}'", stderr)

    def test_github_actions_helpers_emit_plain_text_outside_actions(self) -> None:
        """GitHub Actions helpers should fall back to plain-text local output outside Actions."""

        stdout = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(stdout):
                github_actions.set_output("answer", "42")
                github_actions.emit_annotation("notice", "hello")
                github_actions.start_group("Local Group")
                github_actions.end_group()

        self.assertEqual(stdout.getvalue(), "hello\n=== Local Group ===\n\n")

    def test_github_actions_helpers_emit_annotations_and_outputs_in_actions(self) -> None:
        """GitHub Actions helpers should emit annotations and step outputs inside Actions."""

        stdout = io.StringIO()
        with tempfile.NamedTemporaryFile() as output_file:
            with patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_OUTPUT": output_file.name,
                },
                clear=False,
            ):
                with redirect_stdout(stdout):
                    github_actions.set_output("answer", "42")
                    github_actions.emit_annotation("notice", "hello")
                    github_actions.start_group("Workflow Group")
                    github_actions.end_group()

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(
            stdout.getvalue(),
            "::notice::hello\n::group::Workflow Group\n::endgroup::\n",
        )
        self.assertIn("answer=42\n", written)

    def test_logging_utils_use_standard_logger_outside_github_actions(self) -> None:
        """Logging helpers should route through the standard logger outside Actions."""

        with patch.object(logging_utils.github_actions, "is_github_actions", return_value=False):
            with patch.object(logging_utils.LOGGER, "info") as info_log:
                with patch.object(logging_utils.LOGGER, "warning") as warning_log:
                    with patch.object(logging_utils.LOGGER, "error") as error_log:
                        logging_utils.log_info("plain info")
                        logging_utils.log_warning("plain warning")
                        logging_utils.log_error("plain error")
                        logging_utils.log_success("plain success")

        info_log.assert_any_call("plain info")
        info_log.assert_any_call("[SUCCESS] plain success")
        warning_log.assert_called_once_with("plain warning")
        error_log.assert_called_once_with("plain error")

    def test_logging_utils_emit_annotations_in_github_actions(self) -> None:
        """Logging helpers should emit GitHub annotations inside Actions."""

        with patch.object(logging_utils.github_actions, "is_github_actions", return_value=True):
            with patch.object(logging_utils.github_actions, "emit_annotation") as emit_annotation:
                logging_utils.log_info("workflow info")
                logging_utils.log_warning("workflow warning")
                logging_utils.log_error("workflow error")
                logging_utils.log_success("workflow success")

        self.assertEqual(
            [call.args for call in emit_annotation.call_args_list],
            [
                ("notice", "workflow info"),
                ("warning", "workflow warning"),
                ("error", "workflow error"),
                ("notice", "[SUCCESS] workflow success"),
            ],
        )

    def test_validate_container_reports_size_and_platform(self) -> None:
        """Container validation should return the computed image size."""

        env = {
            "IMAGE_TAG": "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-amd64",
            "PLATFORM": "linux/amd64",
            "MAX_SIZE_MB": "2048",
        }

        pull_result = subprocess.CompletedProcess(args=["docker", "pull"], returncode=0)
        inspect_result = subprocess.CompletedProcess(
            args=["docker", "image", "inspect"],
            returncode=0,
            stdout=str(512 * 1024 * 1024),
        )
        create_result = subprocess.CompletedProcess(
            args=["docker", "create"],
            returncode=0,
            stdout="container-123\n",
        )
        rm_result = subprocess.CompletedProcess(args=["docker", "rm"], returncode=0)

        with patch.dict(os.environ, env, clear=False):
            with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                with patch.object(
                    orchestration,
                    "_run_command",
                    side_effect=[pull_result, inspect_result, create_result, rm_result],
                ):
                    result = adapters.validate_container_from_env()

        self.assertEqual(result.image_tag, env["IMAGE_TAG"])
        self.assertEqual(result.platform, env["PLATFORM"])
        self.assertEqual(result.image_size_mb, 512)

    def test_validate_container_from_env_uses_metadata_mode_without_pull(self) -> None:
        """Workflow validation adapter should support metadata-mode validation paths."""

        with patch.object(orchestration, "detect_container_engine", return_value="docker"):
            with patch.object(orchestration, "_run_image_validation", return_value=256) as run_validation:
                result = adapters.validate_container_from_env(
                    {
                        "IMAGE_TAG": "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-amd64",
                        "PLATFORM": "linux/amd64",
                        "MAX_SIZE_MB": "2048",
                        "VALIDATION_MODE": "metadata",
                    }
                )

        self.assertEqual(result.image_size_mb, 256)
        run_validation.assert_called_once_with(
            "metadata",
            container_engine="docker",
            image_tag="ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-amd64",
            target_platform="linux/amd64",
            max_size_mb=2048,
            pre_message="Running container validation...",
            skip_message="Skipping validation (validation mode: none)",
            quick_success_message="Quick container validation passed",
            metadata_success_message="Metadata-only container validation passed",
            full_success_message="Container validation passed",
            return_image_size=True,
        )

    def test_full_build_validation_uses_local_image_without_pull(self) -> None:
        """Build-path full validation should validate the local image without re-pulling it."""

        inspect_result = subprocess.CompletedProcess(
            args=["docker", "image", "inspect"],
            returncode=0,
            stdout=str(512 * 1024 * 1024),
        )
        create_result = subprocess.CompletedProcess(
            args=["docker", "create"],
            returncode=0,
            stdout="container-123\n",
        )
        rm_result = subprocess.CompletedProcess(args=["docker", "rm"], returncode=0)
        seen_commands: list[list[str]] = []

        def fake_run_command(
            command: list[str],
            *,
            capture_output: bool = False,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            del capture_output, cwd, env
            seen_commands.append(command)
            if command[:3] == ["docker", "image", "inspect"]:
                return inspect_result
            if command[:2] == ["docker", "create"]:
                return create_result
            if command[:2] == ["docker", "rm"]:
                return rm_result
            self.fail(f"Unexpected command: {command}")

        with patch.object(orchestration, "_run_command", side_effect=fake_run_command):
            image_size_mb = orchestration._run_image_validation(
                "full",
                container_engine="docker",
                image_tag=f"localhost:5000/sst-core:15.1.2-{self.host_arch}",
                target_platform=self.host_platform,
                max_size_mb=2048,
                return_image_size=True,
                pull_image=False,
            )

        self.assertEqual(image_size_mb, 512)
        self.assertFalse(any(command[:2] == ["docker", "pull"] for command in seen_commands))

    def test_metadata_validate_image_skips_runtime_env_warning_for_dev_profile(self) -> None:
        """Development-image metadata validation should not warn about missing SST runtime env vars."""

        metadata = {
            "Size": 268435456,
            "Architecture": "arm64",
            "Config": {
                "Env": [
                    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ]
            },
            "RootFS": {"Layers": ["sha256:abc"]},
        }

        with patch.object(orchestration, "_inspect_image_json", return_value=metadata):
            with patch.object(orchestration, "log_warning") as log_warning:
                orchestration.metadata_validate_image(
                    "docker",
                    "localhost:5000/sst-dev:latest-arm64",
                    4096,
                    validation_profile="development",
                )

        log_warning.assert_not_called()

    def test_build_custom_derives_tag_from_core_ref_when_suffix_not_set(self) -> None:
        """Local source-backed builds should derive tag suffix from sst_core_ref when tag_suffix_set=False."""

        request = orchestration.BuildRequest(
            container_type="custom",
            target_platform=self.host_platform,
            validation_mode="metadata",
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            tag_suffix_set=False,
            sst_core_ref="main",
            container_engine="docker",
        )
        build_result = subprocess.CompletedProcess(args=["docker", "build"], returncode=0)
        inspect_result = subprocess.CompletedProcess(
            args=["docker", "image", "inspect"],
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "Size": 268435456,
                        "Architecture": "amd64",
                        "Config": {"Env": ["PATH=/opt/sst/bin:/opt/mpi/bin"]},
                        "RootFS": {"Layers": ["sha256:abc"]},
                    }
                ]
            ),
        )

        with patch.object(orchestration, "detect_container_engine", return_value="docker"):
            with patch.object(orchestration, "_download_build_sources"):
                with patch.object(orchestration, "_write_last_built_image"):
                    with patch.object(
                        orchestration,
                        "_run_command",
                        side_effect=[build_result, inspect_result, inspect_result],
                    ):
                        result = orchestration.build(request)

        self.assertIn("main", result.image_tag)
        self.assertEqual(result.image_size_mb, 256)

    def test_build_accepts_explicit_request(self) -> None:
        """Build should be callable without routing through environment variables."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "Containerfiles").mkdir()
            (repo_root / "Containerfiles" / "Containerfile.dev").write_text(
                "FROM ubuntu:22.04\n",
                encoding="utf-8",
            )

            request = orchestration.BuildRequest(
                container_type="dev",
                target_platform=self.host_platform,
                validation_mode="metadata",
                registry="ghcr.io/hpc-ai-adv-dev",
                sst_version="15.1.2",
                sst_elements_version="15.1.2",
                mpich_version="4.0.2",
                build_ncpus="4",
                tag_suffix="latest",
                tag_suffix_set=False,
                container_engine="docker",
            )
            build_result = subprocess.CompletedProcess(args=["docker", "build"], returncode=0)
            inspect_result = subprocess.CompletedProcess(
                args=["docker", "image", "inspect"],
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "Size": 268435456,
                            "Architecture": "amd64",
                            "Config": {"Env": ["PATH=/opt/sst/bin:/opt/mpi/bin"]},
                            "RootFS": {"Layers": ["sha256:abc"]},
                        }
                    ]
                ),
            )

            with patch.object(orchestration, "REPO_ROOT", repo_root):
                with patch.object(orchestration, "_download_build_sources"):
                    with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                        with patch.object(
                            orchestration,
                            "_run_command",
                            side_effect=[build_result, inspect_result, inspect_result],
                        ):
                            result = orchestration.build(request)

        self.assertEqual(result.container_type, "dev")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
        )
        self.assertEqual(result.image_size_mb, 256)

    def test_plan_build_spec_captures_release_inputs(self) -> None:
        """Standard local builds should produce a reusable build spec."""

        request = orchestration.BuildRequest(
            container_type="full",
            target_platform=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            sst_version="15.1.2",
            sst_elements_version="15.1.0",
            mpich_version="4.0.2",
            build_ncpus="4",
            tag_suffix="latest",
            tag_suffix_set=False,
            enable_perf_tracking=True,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertIsInstance(spec, build_spec.BuildSpec)
        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.container_type, "full")
        self.assertEqual(spec.source.source_kind, "release-tarballs")
        self.assertEqual(spec.tag_suffix, "15.1.2")
        self.assertEqual(spec.verification.max_size_mb, 4096)
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_sst_core)
        self.assertTrue(source_download.download_sst_elements)
        self.assertEqual(spec.primary_platform_build.build_target, "sst-full")
        self.assertIn("SSTver=15.1.2", spec.primary_platform_build.build_args)
        self.assertIn("SST_ELEMENTS_VERSION=15.1.0", spec.primary_platform_build.build_args)
        self.assertIn("ENABLE_PERF_TRACKING=1", spec.primary_platform_build.build_args)
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-perf-track-full:15.1.2-{self.host_arch}",
        )

    def test_plan_build_spec_captures_core_release_inputs(self) -> None:
        """Core local builds should plan the standard release image path."""

        request = orchestration.BuildRequest(
            container_type="core",
            target_platform=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            sst_version="15.1.2",
            mpich_version="4.0.2",
            build_ncpus="4",
            tag_suffix="latest",
            tag_suffix_set=False,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.container_type, "core")
        self.assertEqual(spec.tag_suffix, "15.1.2")
        self.assertEqual(spec.source.source_kind, "release-tarballs")
        self.assertEqual(spec.primary_platform_build.build_target, "sst-core")
        self.assertIn("SSTver=15.1.2", spec.primary_platform_build.build_args)
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-{self.host_arch}",
        )
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_sst_core)
        self.assertFalse(source_download.download_sst_elements)

    def test_plan_build_spec_captures_full_source_build_from_local_checkout(self) -> None:
        """Build spec planning should encode local-checkout source inputs and build arguments."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "sst-core"
            source_dir.mkdir()
            (source_dir / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source_dir / "configure.ac").write_text("AC_INIT([sst-core],[test])\n", encoding="utf-8")

            request = orchestration.BuildRequest(
                container_type="custom",
                target_platform=self.host_platform,
                tag_suffix="local-main-full",
                tag_suffix_set=True,
                sst_core_path=str(source_dir),
                sst_elements_repo="https://github.com/sstsimulator/sst-elements.git",
                sst_elements_ref="main",
                enable_perf_tracking=True,
                validation_mode="metadata",
                registry="ghcr.io/hpc-ai-adv-dev",
            )

            spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.source.source_kind, "local-checkout")
        self.assertTrue(spec.source.uses_local_core_checkout)
        self.assertEqual(spec.primary_platform_build.build_target, "full-build")
        self.assertIn(
            "SST_CORE_SOURCE_STAGE=sst-core-local-source",
            spec.primary_platform_build.build_args,
        )
        self.assertIn(
            "SSTElementsRepo=https://github.com/sstsimulator/sst-elements.git",
            spec.primary_platform_build.build_args,
        )
        self.assertIn("elementsTag=main", spec.primary_platform_build.build_args)
        self.assertIn("ENABLE_PERF_TRACKING=1", spec.primary_platform_build.build_args)
        self.assertEqual(
            spec.primary_platform_build.additional_contexts,
            (
                f"sst_core_input={self.repo_root / '.build-contexts' / 'sst-core-input'}",
            ),
        )
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-perf-track-custom:local-main-full-{self.host_arch}",
        )

    def test_plan_build_spec_captures_full_source_build_from_git_ref(self) -> None:
        """Source build planning should cover the normal git-ref full-build path."""

        request = orchestration.BuildRequest(
            container_type="custom",
            target_platform=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            sst_core_ref="main",
            sst_elements_ref="main",
            tag_suffix="latest",
            tag_suffix_set=False,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.source.source_kind, "git-ref")
        self.assertFalse(spec.source.uses_local_core_checkout)
        self.assertEqual(
            spec.source.sst_elements_repo,
            orchestration.DEFAULT_SST_ELEMENTS_REPO,
        )
        self.assertEqual(spec.primary_platform_build.build_target, "full-build")
        self.assertIn(
            f"SSTrepo={orchestration.DEFAULT_SST_CORE_REPO}",
            spec.primary_platform_build.build_args,
        )
        self.assertIn("tag=main", spec.primary_platform_build.build_args)
        self.assertIn(
            f"SSTElementsRepo={orchestration.DEFAULT_SST_ELEMENTS_REPO}",
            spec.primary_platform_build.build_args,
        )
        self.assertIn("elementsTag=main", spec.primary_platform_build.build_args)
        self.assertEqual(spec.primary_platform_build.additional_contexts, ())
        self.assertEqual(spec.tag_suffix, "main-full")
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-custom:main-full-{self.host_arch}",
        )

    def test_plan_build_spec_resolves_experiment_template_build(self) -> None:
        """Build spec planning should capture template experiment builds and base images."""

        request = orchestration.BuildRequest(
            container_type="experiment",
            target_platform=self.host_platform,
            experiment_name="phold-example",
            base_image="sst-core:latest",
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            tag_suffix_set=True,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.source.source_kind, "experiment-template")
        self.assertFalse(spec.source.uses_custom_containerfile)
        self.assertEqual(
            spec.source.base_image,
            f"ghcr.io/{os.environ.get('USER', '')}/sst-core:latest",
        )
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            str(self.repo_root / "Containerfiles" / "Containerfile.experiment"),
        )
        self.assertIn(
            f"BASE_IMAGE=ghcr.io/{os.environ.get('USER', '')}/sst-core:latest",
            spec.primary_platform_build.build_args,
        )
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/phold-example:latest-{self.host_arch}",
        )

    def test_plan_build_spec_resolves_experiment_custom_containerfile_build(self) -> None:
        """Build spec planning should cover experiments with their own Containerfile."""

        request = orchestration.BuildRequest(
            container_type="experiment",
            target_platform=self.host_platform,
            experiment_name="ahp-graph",
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            tag_suffix_set=True,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.container_type, "experiment")
        self.assertEqual(spec.source.source_kind, "experiment-custom-containerfile")
        self.assertTrue(spec.source.uses_custom_containerfile)
        self.assertEqual(spec.source.base_image, "sst-core:latest")
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            str(self.repo_root / "experiments" / "ahp-graph" / "Containerfile"),
        )
        self.assertEqual(
            spec.primary_platform_build.docker_context,
            str(self.repo_root / "experiments" / "ahp-graph"),
        )
        self.assertEqual(spec.primary_platform_build.build_args, ())
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/ahp-graph:latest-{self.host_arch}",
        )

    def test_plan_build_spec_for_dev_uses_dev_containerfile_and_latest_tag(self) -> None:
        """Development build planning should use the dev containerfile and default latest tag."""

        request = orchestration.BuildRequest(
            container_type="dev",
            target_platform=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            mpich_version="4.0.2",
            build_ncpus="4",
            tag_suffix="latest",
            tag_suffix_set=False,
            validation_mode="metadata",
        )

        spec = orchestration.plan_build_spec(request)

        self.assertEqual(spec.build_kind, "local")
        self.assertEqual(spec.container_type, "dev")
        self.assertEqual(spec.tag_suffix, "latest")
        self.assertEqual(spec.source.source_kind, "development-dependencies")
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            str(self.repo_root / "Containerfiles" / "Containerfile.dev"),
        )
        self.assertEqual(spec.primary_platform_build.build_target, "")
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
        )
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_mpich)
        self.assertFalse(source_download.download_sst_core)

    def test_validate_build_image_uses_development_profile_for_dev_builds(self) -> None:
        """Development build validation should use the development metadata profile."""

        build_spec_value = orchestration.plan_build_spec(
            orchestration.BuildRequest(
                container_type="dev",
                target_platform=self.host_platform,
                registry="ghcr.io/hpc-ai-adv-dev",
                mpich_version="4.0.2",
                build_ncpus="4",
                tag_suffix="latest",
                tag_suffix_set=False,
                validation_mode="none",
            )
        )

        with patch.object(orchestration, "_run_image_validation", return_value=None) as run_validation:
            result = orchestration._validate_build_image(
                build_spec=build_spec_value,
                container_engine="docker",
                image_tag=f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
                target_platform=self.host_platform,
            )

        self.assertIsNone(result)
        run_validation.assert_called_once_with(
            "none",
            container_engine="docker",
            image_tag=f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
            target_platform=self.host_platform,
            max_size_mb=build_spec_value.verification.max_size_mb,
            validation_profile="development",
            skip_message="Skipping validation (validation mode: none)",
            quick_success_message="Quick container validation passed",
            metadata_success_message="Metadata-only container validation passed",
            full_success_message="Container validation passed",
            return_image_size=True,
        )

    def test_plan_workflow_build_spec_for_release_full(self) -> None:
        """Workflow planning should capture release builds without YAML-side reconstruction."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="full",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64,linux/arm64",
                tag_suffix="15.1.2",
                registry="ghcr.io",
                sst_version="15.1.2",
                sst_elements_version="15.1.0",
                mpich_version="4.0.2",
                build_ncpus="2",
                enable_perf_tracking=True,
                no_cache=True,
            )
        )

        self.assertEqual(spec.build_kind, "workflow")
        self.assertEqual(
            spec.publication.manifest_tag,
            "ghcr.io/hpc-ai-adv-dev/sst-perf-track-full:15.1.2",
        )
        self.assertEqual(len(spec.platform_builds), 2)
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            "Containerfiles/Containerfile",
        )
        self.assertEqual(spec.primary_platform_build.build_target, "sst-full")
        self.assertIn("SSTver=15.1.2", spec.primary_platform_build.build_args)
        self.assertIn(
            "SST_ELEMENTS_VERSION=15.1.0",
            spec.primary_platform_build.build_args,
        )
        self.assertIn("ENABLE_PERF_TRACKING=1", spec.primary_platform_build.build_args)
        self.assertTrue(spec.primary_platform_build.no_cache)
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_sst_core)
        self.assertTrue(source_download.download_sst_elements)
        self.assertEqual(spec.verification.mode, "full")
        self.assertEqual(spec.verification.max_size_mb, 4096)

    def test_plan_workflow_build_spec_emits_latest_alias_tag(self) -> None:
        """Release workflow planning should emit latest aliases when requested."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="core",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64,linux/arm64",
                tag_suffix="15.1.2",
                registry="ghcr.io",
                sst_version="15.1.2",
                tag_as_latest=True,
            )
        )

        self.assertEqual(
            spec.publication.alias_tags,
            ("ghcr.io/hpc-ai-adv-dev/sst-core:latest",),
        )

    def test_plan_workflow_build_spec_for_git_ref_core_build(self) -> None:
        """Workflow planning should handle git-ref builds that still publish as core images."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="core",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64,linux/arm64",
                tag_suffix="master-abc1234",
                registry="ghcr.io",
                sst_core_repo="https://github.com/sstsimulator/sst-core.git",
                sst_core_ref="abc1234",
                mpich_version="4.0.2",
                build_ncpus="2",
            )
        )

        self.assertEqual(
            spec.publication.manifest_tag,
            "ghcr.io/hpc-ai-adv-dev/sst-core:master-abc1234",
        )
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            "Containerfiles/Containerfile.tag",
        )
        self.assertEqual(spec.primary_platform_build.build_target, "core-build")
        self.assertIn(
            "SSTrepo=https://github.com/sstsimulator/sst-core.git",
            spec.primary_platform_build.build_args,
        )
        self.assertIn("tag=abc1234", spec.primary_platform_build.build_args)
        self.assertEqual(spec.primary_platform_build.additional_contexts, ())
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_mpich)
        self.assertFalse(source_download.download_sst_core)

    def test_plan_workflow_build_spec_for_dev_defaults_latest_tag(self) -> None:
        """Workflow planning should cover the standard development image path."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="dev",
                image_prefix="hpc-ai-adv-dev/sst-dev",
                build_platforms="linux/amd64,linux/arm64",
                registry="ghcr.io",
                mpich_version="4.0.2",
                build_ncpus="2",
            )
        )

        self.assertEqual(spec.build_kind, "workflow")
        self.assertEqual(spec.container_type, "dev")
        self.assertEqual(spec.tag_suffix, "latest")
        self.assertEqual(
            spec.publication.manifest_tag,
            "ghcr.io/hpc-ai-adv-dev/sst-dev:latest",
        )
        self.assertEqual(len(spec.platform_builds), 2)
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            "Containerfiles/Containerfile.dev",
        )
        self.assertEqual(spec.primary_platform_build.build_target, "")
        self.assertEqual(spec.source.source_kind, "development-dependencies")
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_mpich)
        self.assertFalse(source_download.download_sst_core)

    def test_plan_workflow_build_spec_for_custom_experiment_containerfile(self) -> None:
        """Workflow planning should support experiment directories with custom Containerfiles."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="experiment",
                image_prefix="hpc-ai-adv-dev",
                build_platforms="linux/amd64",
                tag_suffix="latest",
                registry="ghcr.io",
                experiment_name="ahp-graph",
            ),
            validate_base_image=False,
        )

        self.assertEqual(spec.build_kind, "workflow")
        self.assertEqual(spec.container_type, "experiment")
        self.assertEqual(
            spec.publication.manifest_tag,
            "ghcr.io/hpc-ai-adv-dev/ahp-graph:latest",
        )
        self.assertEqual(spec.source.source_kind, "experiment-custom-containerfile")
        self.assertTrue(spec.source.uses_custom_containerfile)
        self.assertEqual(
            spec.primary_platform_build.containerfile_path,
            "experiments/ahp-graph/Containerfile",
        )
        self.assertEqual(
            spec.primary_platform_build.docker_context,
            "experiments/ahp-graph",
        )
        self.assertEqual(spec.primary_platform_build.build_args, ())
        self.assertIsNotNone(spec.source_download)
        source_download = spec.source_download
        assert source_download is not None
        self.assertTrue(source_download.download_mpich)
        self.assertFalse(source_download.download_sst_core)

    def test_plan_workflow_build_spec_emits_master_latest_alias_tag(self) -> None:
        """Nightly workflow planning should emit master-latest aliases when requested."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="core",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64,linux/arm64",
                tag_suffix="master-abc1234",
                registry="ghcr.io",
                sst_core_repo="https://github.com/sstsimulator/sst-core.git",
                sst_core_ref="abc1234",
                publish_master_latest=True,
            )
        )

        self.assertEqual(
            spec.publication.alias_tags,
            ("ghcr.io/hpc-ai-adv-dev/sst-core:master-latest",),
        )

    def test_plan_workflow_bake_emits_release_targets(self) -> None:
        """Workflow bake planning should emit structured Buildx targets for release builds."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="full",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64,linux/arm64",
                tag_suffix="15.1.2",
                registry="ghcr.io",
                sst_version="15.1.2",
                sst_elements_version="15.1.0",
                mpich_version="4.0.2",
                build_ncpus="2",
                enable_perf_tracking=True,
                no_cache=True,
            )
        )

        bake_plan = orchestration.plan_workflow_bake(
            spec,
            labels={"com.github.sha": "deadbeef"},
        )

        self.assertEqual(
            tuple(target.name for target in bake_plan.targets),
            ("full-amd64", "full-arm64"),
        )
        target_definitions = cast(dict[str, dict[str, object]], bake_plan.definition["target"])
        amd64_target = target_definitions["full-amd64"]
        self.assertEqual(amd64_target["context"], "Containerfiles")
        self.assertEqual(amd64_target["dockerfile"], "Containerfile")
        self.assertEqual(amd64_target["target"], "sst-full")
        self.assertEqual(amd64_target["platforms"], ["linux/amd64"])
        self.assertEqual(
            amd64_target["tags"],
            ["ghcr.io/hpc-ai-adv-dev/sst-perf-track-full:15.1.2-amd64"],
        )
        args_map = cast(dict[str, str], amd64_target["args"])
        self.assertEqual(args_map["SSTver"], "15.1.2")
        self.assertEqual(args_map["SST_ELEMENTS_VERSION"], "15.1.0")
        self.assertEqual(args_map["ENABLE_PERF_TRACKING"], "1")
        self.assertEqual(
            amd64_target["cache-from"],
            ["type=gha,scope=full-15.1.2-amd64"],
        )
        self.assertEqual(
            amd64_target["cache-to"],
            ["type=gha,mode=max,scope=full-15.1.2-amd64"],
        )
        self.assertTrue(amd64_target["no-cache"])
        labels_map = cast(dict[str, str], amd64_target["labels"])
        self.assertEqual(labels_map["com.github.sha"], "deadbeef")

    def test_plan_workflow_bake_omits_named_context_for_git_ref_builds(self) -> None:
        """Git-ref workflow builds should not emit local-only named contexts."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="core",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64",
                tag_suffix="master-abc1234",
                registry="ghcr.io",
                sst_core_repo="https://github.com/sstsimulator/sst-core.git",
                sst_core_ref="abc1234",
            )
        )

        bake_plan = orchestration.plan_workflow_bake(spec, workspace_root=self.repo_root)
        target_definitions = cast(dict[str, dict[str, object]], bake_plan.definition["target"])
        amd64_target = target_definitions["core-amd64"]
        self.assertNotIn("contexts", amd64_target)

    def test_collect_verified_manifest_images_reports_only_inspectable_platform_tags(self) -> None:
        """Manifest helper should report only platform tags that can be inspected."""

        manifest_tag = "ghcr.io/example/sst-core:15.1.2"

        def fake_inspect(_engine: str, image_ref: str) -> bool:
            return image_ref.endswith("-amd64")

        with patch.object(orchestration, "inspect_remote_manifest", side_effect=fake_inspect):
            with patch.object(orchestration, "log_warning") as log_warning:
                result = orchestration.collect_verified_manifest_images(
                    manifest_tag,
                    "linux/amd64,linux/arm64",
                )

        self.assertEqual(result, (f"{manifest_tag}-amd64",))
        log_warning.assert_called_once()

    def test_collect_verified_manifest_images_returns_empty_tuple_when_manifest_inputs_missing(self) -> None:
        """Manifest helper should short-circuit when required inputs are missing."""

        self.assertEqual(orchestration.collect_verified_manifest_images("", "linux/amd64"), ())
        self.assertEqual(
            orchestration.collect_verified_manifest_images(
                "ghcr.io/example/sst-core:15.1.2",
                "",
            ),
            (),
        )

    def test_stage_local_sst_core_checkout_excludes_ignored_git_artifacts(self) -> None:
        """Git checkout staging should keep local changes but exclude ignored files."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "sst-core"
            stage_dir = Path(temp_dir) / "stage"
            (source_dir / "src" / "sst" / "core").mkdir(parents=True)
            (source_dir / "build").mkdir()
            (source_dir / ".venv").mkdir()
            (source_dir / ".gitignore").write_text("build/\n.venv/\n*.tmp\n", encoding="utf-8")
            (source_dir / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source_dir / "configure.ac").write_text("AC_INIT([sst-core],[test])\n", encoding="utf-8")
            tracked_file = source_dir / "src" / "sst" / "core" / "simulation.h"
            tracked_file.write_text("tracked\n", encoding="utf-8")

            subprocess.run(["git", "init", "-q", str(source_dir)], check=True)
            subprocess.run(["git", "-C", str(source_dir), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(source_dir), "config", "user.name", "Test User"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source_dir),
                    "add",
                    "autogen.sh",
                    "configure.ac",
                    ".gitignore",
                    "src/sst/core/simulation.h",
                ],
                check=True,
            )
            subprocess.run(["git", "-C", str(source_dir), "commit", "-qm", "init"], check=True)

            tracked_file.write_text("tracked\nmodified\n", encoding="utf-8")
            (source_dir / "local-change.txt").write_text("local\n", encoding="utf-8")
            (source_dir / "build" / "output.o").write_text("ignored\n", encoding="utf-8")
            (source_dir / "generated.tmp").write_text("ignored\n", encoding="utf-8")
            (source_dir / ".venv" / "marker").write_text("ignored\n", encoding="utf-8")

            orchestration.stage_local_sst_core_checkout(str(source_dir), stage_dir)

            self.assertTrue((stage_dir / "autogen.sh").is_file())
            self.assertTrue((stage_dir / "configure.ac").is_file())
            self.assertIn(
                "modified",
                (stage_dir / "src" / "sst" / "core" / "simulation.h").read_text(encoding="utf-8"),
            )
            self.assertTrue((stage_dir / "local-change.txt").is_file())
            self.assertFalse((stage_dir / ".git").exists())
            self.assertFalse((stage_dir / "build" / "output.o").exists())
            self.assertFalse((stage_dir / "generated.tmp").exists())
            self.assertFalse((stage_dir / ".venv" / "marker").exists())

    def test_stage_local_sst_core_checkout_excludes_git_metadata_for_plain_tree(self) -> None:
        """Plain directory staging should exclude `.git` metadata."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "sst-core"
            stage_dir = Path(temp_dir) / "stage"
            (source_dir / ".git").mkdir(parents=True)
            (source_dir / "src" / "sst" / "core").mkdir(parents=True)
            (source_dir / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source_dir / "configure.ac").write_text("AC_INIT([sst-core],[test])\n", encoding="utf-8")
            (source_dir / "src" / "sst" / "core" / "simulation.h").write_text("tracked\n", encoding="utf-8")
            (source_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

            orchestration.stage_local_sst_core_checkout(str(source_dir), stage_dir)

            self.assertTrue((stage_dir / "autogen.sh").is_file())
            self.assertTrue((stage_dir / "configure.ac").is_file())
            self.assertTrue((stage_dir / "src" / "sst" / "core" / "simulation.h").is_file())
            self.assertFalse((stage_dir / ".git").exists())

    def test_reset_local_source_stage_dir_restores_placeholder_layout(self) -> None:
        """Resetting a stage directory should recreate only the placeholder marker."""

        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir) / "stage"
            (stage_dir / "subdir").mkdir(parents=True)
            (stage_dir / "subdir" / "file.txt").write_text("stale\n", encoding="utf-8")

            orchestration.reset_local_source_stage_dir(stage_dir)

            self.assertTrue((stage_dir / ".gitkeep").is_file())
            self.assertFalse((stage_dir / "subdir" / "file.txt").exists())

    def test_prepare_workflow_build_from_env_writes_matrix_outputs(self) -> None:
        """The workflow planner adapter should emit a matrix and source-download outputs."""

        with tempfile.NamedTemporaryFile() as output_file:
            env = {
                "CONTAINER_TYPE": "core",
                "IMAGE_PREFIX": "hpc-ai-adv-dev/sst",
                "BUILD_PLATFORMS": "linux/amd64,linux/arm64",
                "TAG_SUFFIX": "15.1.2",
                "REGISTRY": "ghcr.io",
                "SST_VERSION": "15.1.2",
                "MPICH_VERSION": "4.0.2",
                "BUILD_NCPUS": "2",
                "GITHUB_OUTPUT": output_file.name,
            }
            with patch.dict(os.environ, env, clear=False):
                spec = adapters.prepare_workflow_build_from_env()

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(
            spec.publication.manifest_tag,
            "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2",
        )
        self.assertIn("manifest_tag=ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2", written)
        self.assertIn("resolved_tag_suffix=15.1.2", written)
        self.assertIn("validation_mode=full", written)
        self.assertIn("max_image_size_mb=2048", written)
        self.assertIn("download_sst_core=true", written)
        self.assertIn("download_sst_elements=false", written)
        platform_matrix_line = next(
            line for line in written.splitlines() if line.startswith("platform_matrix=")
        )
        platform_matrix = json.loads(platform_matrix_line.split("=", 1)[1])
        self.assertEqual(len(platform_matrix["include"]), 2)
        self.assertEqual(
            platform_matrix["include"][0]["bake_target"],
            "core-amd64",
        )
        bake_definition_line = next(
            line for line in written.splitlines() if line.startswith("bake_definition_json=")
        )
        bake_definition = json.loads(bake_definition_line.split("=", 1)[1])
        self.assertEqual(
            bake_definition["target"]["core-amd64"]["dockerfile"],
            "Containerfile",
        )
        alias_tags_line = next(
            line for line in written.splitlines() if line.startswith("alias_tags_json=")
        )
        self.assertEqual(json.loads(alias_tags_line.split("=", 1)[1]), [])

    def test_plan_workflow_bake_emits_absolute_template_dockerfile_outside_context(self) -> None:
        """Experiment template builds should keep Dockerfiles outside the context workspace-absolute."""

        spec = orchestration.plan_workflow_build_spec(
            orchestration.WorkflowBuildRequest(
                container_type="experiment",
                image_prefix="hpc-ai-adv-dev/sst",
                build_platforms="linux/amd64",
                tag_suffix="latest",
                registry="ghcr.io",
                experiment_name="phold-example",
                base_image="sst-core:latest",
            ),
            validate_base_image=False,
        )

        bake_plan = orchestration.plan_workflow_bake(spec)
        target_definitions = cast(dict[str, dict[str, object]], bake_plan.definition["target"])
        amd64_target = target_definitions["experiment-amd64"]

        self.assertEqual(amd64_target["context"], "experiments/phold-example")
        self.assertEqual(
            amd64_target["dockerfile"],
            str(self.repo_root / "Containerfiles" / "Containerfile.experiment"),
        )

if __name__ == "__main__":
    unittest.main()
