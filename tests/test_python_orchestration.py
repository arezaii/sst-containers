"""Unit tests for the Python-backed orchestration helpers."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from typing import cast
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sst_container_factory import adapters, build_spec, cli, orchestration


class OrchestrationTests(unittest.TestCase):
    """Validate the Python orchestration transition layer."""

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the repository root once for shim tests."""

        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.host_platform = orchestration.detect_host_platform()
        cls.host_arch = orchestration.platform_to_arch(cls.host_platform)

    def _run_shim(
        self,
        script_relative_path: str,
        env_updates: dict[str, str],
        args: list[str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a shell shim with the repository Python interpreter wired in."""

        env = os.environ.copy()
        env.update(
            {
                "PYTHON_BIN": sys.executable,
                "PYTHONPATH": str(self.repo_root),
            }
        )
        env.update(env_updates)

        return subprocess.run(
            [str(self.repo_root / script_relative_path), *(args or [])],
            cwd=cwd or self.repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

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

    def test_download_tarballs_downloads_requested_artifacts(self) -> None:
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
                result = orchestration.download_tarballs(
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

    def test_cli_download_tarballs_maps_explicit_selection(self) -> None:
        """The Python CLI should translate downloader options into explicit request flags."""

        with patch.object(cli, "download_tarballs") as download_tarballs:
            status = cli.main(
                [
                    "download-tarballs",
                    "--sst-version",
                    "15.1.2",
                    "--sst-elements-version",
                    "15.1.0",
                    "--force",
                ]
            )

        self.assertEqual(status, 0)
        download_tarballs.assert_called_once_with(
            sst_version="15.1.2",
            sst_elements_version="15.1.0",
            mpich_version=orchestration.DEFAULT_MPICH_VERSION,
            download_mpich=False,
            download_sst_core=True,
            download_sst_elements=True,
            force_mode=True,
        )

    def test_cli_experiment_build_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit experiment-build arguments."""

        with patch.object(cli, "experiment_build") as experiment_build:
            status = cli.main(
                [
                    "experiment-build",
                    "--base-image",
                    "sst-core:latest",
                    "--platforms",
                    self.host_platform,
                    "--build-arg",
                    "EXTRA=1",
                    "--validation",
                    "metadata",
                    "--engine",
                    "docker",
                    "phold-example",
                ]
            )

        self.assertEqual(status, 0)
        request = experiment_build.call_args.args[0]
        self.assertIsInstance(request, orchestration.ExperimentBuildRequest)
        self.assertEqual(request.experiment_name, "phold-example")
        self.assertEqual(request.build_platforms, self.host_platform)
        self.assertEqual(request.build_args, ("EXTRA=1",))
        self.assertEqual(request.validation_mode, "metadata")
        self.assertEqual(request.container_engine, "docker")

    def test_cli_custom_build_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit custom-build arguments."""

        with patch.object(cli, "custom_build") as custom_build:
            status = cli.main(
                [
                    "custom-build",
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
        request = custom_build.call_args.args[0]
        self.assertIsInstance(request, orchestration.CustomBuildRequest)
        self.assertEqual(request.sst_core_ref, "main")
        self.assertEqual(request.target_platform, self.host_platform)
        self.assertEqual(request.tag_suffix, "demo")
        self.assertEqual(request.validation_mode, "metadata")
        self.assertTrue(request.enable_perf_tracking)
        self.assertEqual(request.container_engine, "docker")

    def test_cli_local_build_dispatches_explicit_request(self) -> None:
        """The Python CLI should accept explicit local-build arguments."""

        with patch.object(cli, "local_build") as local_build:
            status = cli.main(
                [
                    "local-build",
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
        request = local_build.call_args.args[0]
        self.assertIsInstance(request, orchestration.LocalBuildRequest)
        self.assertEqual(request.container_type, "core")
        self.assertEqual(request.target_platform, self.host_platform)
        self.assertEqual(request.sst_version, "15.1.2")
        self.assertEqual(request.tag_suffix, "demo")
        self.assertTrue(request.tag_suffix_set)
        self.assertEqual(request.validation_mode, "metadata")
        self.assertTrue(request.cleanup)
        self.assertEqual(request.container_engine, "docker")

    def test_cli_custom_build_rejects_mutually_exclusive_core_source_flags(self) -> None:
        """The Python CLI should let argparse enforce core source mutual exclusion."""

        status, _stdout, stderr = self._run_python_cli(
            [
                "custom-build",
                "--core-path",
                "/tmp/sst-core",
                "--core-ref",
                "main",
            ]
        )

        self.assertEqual(status, 1)
        self.assertIn("not allowed with argument --core-path", stderr)

    def test_cli_experiment_build_rejects_invalid_validation_mode(self) -> None:
        """The Python CLI should let argparse choices enforce validation modes."""

        status, _stdout, stderr = self._run_python_cli(
            [
                "experiment-build",
                "--validation",
                "no-exec",
                "phold-example",
            ]
        )

        self.assertEqual(status, 1)
        self.assertIn("invalid choice: 'no-exec'", stderr)

    def test_cli_experiment_build_requires_experiment_name(self) -> None:
        """The experiment-build parser should require the experiment name positional."""

        status, _stdout, stderr = self._run_python_cli(["experiment-build"])

        self.assertEqual(status, 1)
        self.assertIn("the following arguments are required: EXPERIMENT_NAME", stderr)

    def test_cli_local_build_rejects_invalid_container_type(self) -> None:
        """The Python CLI should let argparse enforce local-build container choices."""

        status, _stdout, stderr = self._run_python_cli(["local-build", "not-a-type"])

        self.assertEqual(status, 1)
        self.assertIn("argument CONTAINER_TYPE: invalid choice: 'not-a-type'", stderr)

    def test_cli_local_build_dev_rejects_perf_tracking_flag(self) -> None:
        """The dev local-build subparser should reject perf tracking at parse time."""

        status, _stdout, stderr = self._run_python_cli(
            ["local-build", "dev", "--enable-perf-tracking"]
        )

        self.assertEqual(status, 1)
        self.assertIn("unrecognized arguments: --enable-perf-tracking", stderr)

    def test_prepare_image_config_generates_expected_outputs(self) -> None:
        """Prepare-image-config should compute the expected patterns."""

        with tempfile.NamedTemporaryFile() as output_file:
            env = {
                "CONTAINER_TYPE": "core",
                "IMAGE_PREFIX": "hpc-ai-adv-dev/sst",
                "TAG_SUFFIX": "15.1.2",
                "REGISTRY": "ghcr.io",
                "GITHUB_OUTPUT": output_file.name,
            }
            with patch.dict(os.environ, env, clear=False):
                result = adapters.prepare_image_config_from_env()

            self.assertEqual(result.image_prefix, "hpc-ai-adv-dev/sst")
            self.assertEqual(
                result.core_full_pattern,
                "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2",
            )

            written = Path(output_file.name).read_text(encoding="utf-8")
            self.assertIn("image_prefix=hpc-ai-adv-dev/sst", written)
            self.assertIn(
                "core_full_pattern=ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2",
                written,
            )

    def test_validate_custom_inputs_requires_elements_ref_for_full_build(self) -> None:
        """Custom input validation should reject incomplete full-build requests."""

        env = {
            "CORE_REF": "feature/test",
            "ELEMENTS_REPO": "https://github.com/sstsimulator/sst-elements.git",
            "ELEMENTS_REF": "",
            "IMAGE_TAG": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ValueError):
                adapters.validate_custom_inputs_from_env()

    def test_validate_experiment_inputs_detects_containerfile(self) -> None:
        """Experiment validation should accept directories with a custom Containerfile."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            experiment_dir = repo_root / "demo-experiment"
            experiment_dir.mkdir()
            (experiment_dir / "Containerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
            (experiment_dir / "README.md").write_text("demo\n", encoding="utf-8")

            env = {
                "EXPERIMENT_NAME": "demo-experiment",
                "BASE_IMAGE": "sst-core:latest",
                "REPO_OWNER": "hpc-ai-adv-dev",
            }
            with patch.dict(os.environ, env, clear=False):
                with patch.object(orchestration, "REPO_ROOT", repo_root):
                    with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                        result = adapters.validate_experiment_inputs_from_env()

            self.assertTrue(result.experiment_exists)
            self.assertTrue(result.has_containerfile)
            self.assertEqual(result.resolved_base_image, "")
            self.assertEqual(result.files_count, 2)

    def test_validate_experiment_inputs_resolves_short_base_image(self) -> None:
        """Experiment validation should resolve short GHCR image names."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            experiment_dir = repo_root / "demo-experiment"
            experiment_dir.mkdir()
            (experiment_dir / "run.sh").write_text("echo demo\n", encoding="utf-8")

            env = {
                "EXPERIMENT_NAME": "demo-experiment",
                "BASE_IMAGE": "sst-core:latest",
                "REPO_OWNER": "hpc-ai-adv-dev",
            }
            with patch.dict(os.environ, env, clear=False):
                with patch.object(orchestration, "REPO_ROOT", repo_root):
                    with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                        with patch.object(orchestration, "inspect_remote_manifest", return_value=True):
                            result = adapters.validate_experiment_inputs_from_env()

            self.assertTrue(result.experiment_exists)
            self.assertFalse(result.has_containerfile)
            self.assertEqual(
                result.resolved_base_image,
                "ghcr.io/hpc-ai-adv-dev/sst-core:latest",
            )
            self.assertEqual(result.files_count, 1)

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

    def test_validate_container_shim_executes_python_library(self) -> None:
        """The shell shim should dispatch into the Python validator."""

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_engine = Path(temp_dir) / "docker"
            fake_engine.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "command=${1:?}\n"
                "shift\n"
                "case \"$command\" in\n"
                "  pull)\n"
                "    exit 0\n"
                "    ;;\n"
                "  image)\n"
                "    subcommand=${1:?}\n"
                "    shift\n"
                "    if [ \"$subcommand\" = \"inspect\" ]; then\n"
                "      printf '268435456\\n'\n"
                "      exit 0\n"
                "    fi\n"
                "    exit 1\n"
                "    ;;\n"
                "  create)\n"
                "    printf 'container-456\\n'\n"
                "    exit 0\n"
                "    ;;\n"
                "  rm)\n"
                "    exit 0\n"
                "    ;;\n"
                "esac\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_engine.chmod(fake_engine.stat().st_mode | stat.S_IXUSR)

            result = self._run_shim(
                "scripts/orchestration/validate-container.sh",
                {
                    "IMAGE_TAG": "example/image:amd64",
                    "PLATFORM": "linux/amd64",
                    "CONTAINER_ENGINE": str(fake_engine),
                },
            )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Container validation passed: 256 MB, linux/amd64", result.stdout)

    def test_prepare_image_config_shim_writes_expected_outputs(self) -> None:
        """The prepare-image-config shim should preserve GitHub output behavior."""

        with tempfile.NamedTemporaryFile() as output_file:
            result = self._run_shim(
                "scripts/orchestration/prepare-image-config.sh",
                {
                    "CONTAINER_TYPE": "core",
                    "IMAGE_PREFIX": "hpc-ai-adv-dev/sst",
                    "TAG_SUFFIX": "15.1.2",
                    "GITHUB_OUTPUT": output_file.name,
                },
            )

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("image_prefix=hpc-ai-adv-dev/sst", written)
        self.assertIn(
            "core_full_pattern=ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2",
            written,
        )

    def test_validate_custom_inputs_shim_writes_expected_outputs(self) -> None:
        """The validate-custom-inputs shim should preserve GitHub output behavior."""

        with tempfile.NamedTemporaryFile() as output_file:
            result = self._run_shim(
                "scripts/orchestration/validate-custom-inputs.sh",
                {
                    "CORE_REF": "feature/test",
                    "GITHUB_OUTPUT": output_file.name,
                },
            )

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("build_type=core", written)
        self.assertIn("tag_suffix=feature-test", written)

    def test_validate_experiment_inputs_shim_detects_custom_containerfile(self) -> None:
        """The validate-experiment-inputs shim should preserve GitHub output behavior."""

        with tempfile.NamedTemporaryFile() as output_file:
            result = self._run_shim(
                "scripts/orchestration/validate-experiment-inputs.sh",
                {
                    "EXPERIMENT_NAME": "ahp-graph",
                    "GITHUB_OUTPUT": output_file.name,
                },
            )

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("experiment_exists=true", written)
        self.assertIn("has_containerfile=true", written)

    def test_experiment_build_from_env_builds_custom_container(self) -> None:
        """Experiment builds should use an experiment-local Containerfile when present."""

        env = {
            "EXPERIMENT_NAME": "ahp-graph",
            "BUILD_PLATFORMS": self.host_platform,
            "REGISTRY": "ghcr.io/hpc-ai-adv-dev",
            "TAG_SUFFIX": "latest",
            "VALIDATION_MODE": "none",
            "NO_CACHE": "false",
            "BUILD_ARGS_SERIALIZED": "",
        }
        build_result = subprocess.CompletedProcess(args=["docker", "build"], returncode=0)

        with patch.dict(os.environ, env, clear=False):
            with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                with patch.object(orchestration, "_run_command", side_effect=[build_result]):
                    result = adapters.experiment_build_from_env()

        self.assertEqual(result.containerfile_type, "custom")
        self.assertEqual(result.containerfile_path, str(self.repo_root / "ahp-graph" / "Containerfile"))
        self.assertEqual(result.docker_context, str(self.repo_root / "ahp-graph"))
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/ahp-graph:latest-{self.host_arch}",
        )

    def test_experiment_build_accepts_explicit_request(self) -> None:
        """Experiment builds should be callable without routing through environment variables."""

        request = orchestration.ExperimentBuildRequest(
            experiment_name="ahp-graph",
            build_platforms=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            validation_mode="none",
            container_engine="docker",
        )
        build_result = subprocess.CompletedProcess(args=["docker", "build"], returncode=0)

        with patch.object(orchestration, "detect_container_engine", return_value="docker"):
            with patch.object(orchestration, "_run_command", side_effect=[build_result]):
                result = orchestration.experiment_build(request)

        self.assertEqual(result.containerfile_type, "custom")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/ahp-graph:latest-{self.host_arch}",
        )

    def test_experiment_build_from_env_metadata_validation_uses_image_inspect(self) -> None:
        """Metadata validation should inspect the built image without creating a container."""

        env = {
            "EXPERIMENT_NAME": "phold-example",
            "BASE_IMAGE": "sst-core:latest",
            "BUILD_PLATFORMS": self.host_platform,
            "REGISTRY": "ghcr.io/hpc-ai-adv-dev",
            "TAG_SUFFIX": "latest",
            "VALIDATION_MODE": "metadata",
            "NO_CACHE": "true",
            "BUILD_ARGS_SERIALIZED": "EXTRA_ARG=value",
        }
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

        with patch.dict(os.environ, env, clear=False):
            with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                with patch.object(orchestration, "inspect_remote_manifest", return_value=True):
                    with patch.object(
                        orchestration,
                        "_run_command",
                        side_effect=[build_result, inspect_result],
                    ):
                        result = adapters.experiment_build_from_env()

        self.assertEqual(result.containerfile_type, "template")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/phold-example:latest-{self.host_arch}",
        )

    def test_experiment_build_shim_completes_metadata_build_with_fake_engine(self) -> None:
        """The experiment-build shell entrypoint should execute the Python-backed build path."""

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_engine = Path(temp_dir) / "fake-engine"
            fake_engine.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "command=${1:?}\n"
                "shift\n"
                "case \"$command\" in\n"
                "  build)\n"
                "    exit 0\n"
                "    ;;\n"
                "  image)\n"
                "    subcommand=${1:?}\n"
                "    shift\n"
                "    if [ \"$subcommand\" = \"inspect\" ]; then\n"
                "      printf '[{\"Size\":268435456,\"Architecture\":\"amd64\",\"Config\":{\"Env\":[\"PATH=/opt/sst/bin:/opt/mpi/bin\"]},\"RootFS\":{\"Layers\":[\"sha256:abc\"]}}]'\n"
                "      exit 0\n"
                "    fi\n"
                "    exit 1\n"
                "    ;;\n"
                "  manifest)\n"
                "    exit 0\n"
                "    ;;\n"
                "esac\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_engine.chmod(fake_engine.stat().st_mode | stat.S_IXUSR)

            result = self._run_shim(
                "scripts/build/experiment-build.sh",
                {"CONTAINER_ENGINE": str(fake_engine)},
                ["--validation", "metadata", "phold-example"],
            )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Experiment build completed successfully!", result.stdout)

    def test_custom_build_from_env_metadata_validation_uses_image_inspect(self) -> None:
        """Custom builds should validate the built image through Python metadata inspection."""

        env = {
            "BUILD_TYPE": "core-build",
            "USING_LOCAL_CORE_CHECKOUT": "false",
            "SST_CORE_REPO": "https://github.com/sstsimulator/sst-core.git",
            "SST_CORE_REF": "main",
            "SST_ELEMENTS_REPO": "",
            "SST_ELEMENTS_REF": "",
            "MPICH_VERSION": "4.0.2",
            "BUILD_NCPUS": "4",
            "TARGET_PLATFORM": self.host_platform,
            "REGISTRY": "ghcr.io/hpc-ai-adv-dev",
            "TAG_SUFFIX": "main",
            "ENABLE_PERF_TRACKING": "false",
            "NO_CACHE": "false",
            "CLEANUP": "false",
            "VALIDATION_MODE": "metadata",
        }
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

        with patch.dict(os.environ, env, clear=False):
            with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                with patch.object(
                    orchestration,
                    "_run_command",
                    side_effect=[build_result, inspect_result, inspect_result],
                ):
                    result = adapters.custom_build_from_env()

        self.assertEqual(result.build_type, "core-build")
        self.assertEqual(result.image_size_mb, 256)
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-custom:main-{self.host_arch}",
        )

    def test_custom_build_accepts_explicit_request(self) -> None:
        """Custom builds should be callable without routing through environment variables."""

        request = orchestration.CustomBuildRequest(
            sst_core_ref="main",
            target_platform=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="main",
            validation_mode="metadata",
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
            with patch.object(
                orchestration,
                "_run_command",
                side_effect=[build_result, inspect_result, inspect_result],
            ):
                result = orchestration.custom_build(request)

        self.assertEqual(result.build_type, "core-build")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-custom:main-{self.host_arch}",
        )

    def test_local_build_custom_delegates_tag_suffix_derivation(self) -> None:
        """Local custom builds should rely on canonical custom-build normalization for defaults."""

        request = orchestration.LocalBuildRequest(
            container_type="custom",
            target_platform=self.host_platform,
            validation_mode="metadata",
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            tag_suffix_set=False,
            sst_core_ref="main",
            container_engine="docker",
        )
        custom_result = orchestration.CustomBuildResult(
            image_tag=f"ghcr.io/hpc-ai-adv-dev/sst-custom:main-{self.host_arch}",
            build_type="core-build",
            image_size_mb=256,
        )

        with patch.object(orchestration, "detect_container_engine", return_value="docker"):
            with patch.object(orchestration, "_download_local_build_sources"):
                with patch.object(orchestration, "custom_build", return_value=custom_result) as custom_build:
                    with patch.object(orchestration, "_write_last_built_image"):
                        with patch.object(
                            orchestration,
                            "_validate_local_build_image",
                            return_value=256,
                        ):
                            result = orchestration.local_build(request)

        delegated_request = custom_build.call_args.args[0]
        self.assertEqual(delegated_request.tag_suffix, "")
        self.assertEqual(delegated_request.sst_core_ref, "main")
        self.assertEqual(result.image_tag, custom_result.image_tag)
        self.assertEqual(result.image_size_mb, 256)

    def test_custom_build_shim_supports_local_core_checkout(self) -> None:
        """The custom-build shell entrypoint should still support local SST-core staging."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "sst-core"
            source_dir.mkdir()
            (source_dir / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source_dir / "configure.ac").write_text("AC_INIT([sst-core],[test])\n", encoding="utf-8")
            (source_dir / "autogen.sh").chmod((source_dir / "autogen.sh").stat().st_mode | stat.S_IXUSR)

            fake_engine = Path(temp_dir) / "docker"
            fake_engine.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "command=${1:?}\n"
                "shift\n"
                "case \"$command\" in\n"
                "  version)\n"
                "    printf 'fake-engine version 1.0\\n'\n"
                "    exit 0\n"
                "    ;;\n"
                "  info)\n"
                "    exit 0\n"
                "    ;;\n"
                "  build)\n"
                "    exit 0\n"
                "    ;;\n"
                "  image)\n"
                "    subcommand=${1:?}\n"
                "    shift\n"
                "    if [ \"$subcommand\" = \"inspect\" ]; then\n"
                "      printf '[{\"Size\":268435456,\"Architecture\":\"amd64\",\"Config\":{\"Env\":[\"PATH=/opt/sst/bin:/opt/mpi/bin\"]},\"RootFS\":{\"Layers\":[\"sha256:abc\"]}}]'\n"
                "      exit 0\n"
                "    fi\n"
                "    exit 1\n"
                "    ;;\n"
                "esac\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_engine.chmod(fake_engine.stat().st_mode | stat.S_IXUSR)

            result = self._run_shim(
                "scripts/build/custom-build.sh",
                {"PATH": f"{temp_dir}:{os.environ.get('PATH', '')}"},
                [
                    "--core-path",
                    str(source_dir),
                    "--validation",
                    "metadata",
                ],
            )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Custom build completed successfully", result.stdout)

    def test_local_build_from_env_builds_dev_image_with_metadata_validation(self) -> None:
        """Local-build should download, build, and validate dev images through Python."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "Containerfiles").mkdir()
            (repo_root / "Containerfiles" / "Containerfile.dev").write_text(
                "FROM ubuntu:22.04\n",
                encoding="utf-8",
            )
            download_script = repo_root / "scripts" / "build" / "download_tarballs.sh"
            download_script.parent.mkdir(parents=True)
            download_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            download_script.chmod(download_script.stat().st_mode | stat.S_IXUSR)

            env = {
                "CONTAINER_TYPE": "dev",
                "VALIDATE_ONLY": "false",
                "VALIDATION_MODE": "metadata",
                "CLEANUP": "false",
                "REGISTRY": "ghcr.io/hpc-ai-adv-dev",
                "SST_VERSION": "15.1.2",
                "SST_ELEMENTS_VERSION": "15.1.2",
                "MPICH_VERSION": "4.0.2",
                "BUILD_NCPUS": "4",
                "TARGET_PLATFORM": self.host_platform,
                "ENABLE_PERF_TRACKING": "false",
                "TAG_SUFFIX": "latest",
                "TAG_SUFFIX_SET": "false",
                "NO_CACHE": "false",
                "DOWNLOAD_SCRIPT": str(download_script),
            }
            download_result = subprocess.CompletedProcess(args=[str(download_script)], returncode=0)
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

            with patch.dict(os.environ, env, clear=False):
                with patch.object(orchestration, "REPO_ROOT", repo_root):
                    with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                        with patch.object(
                            orchestration,
                            "_run_command",
                            side_effect=[download_result, build_result, inspect_result, inspect_result],
                        ):
                            result = adapters.local_build_from_env()

        self.assertEqual(result.container_type, "dev")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
        )
        self.assertEqual(result.image_size_mb, 256)

    def test_local_build_accepts_explicit_request(self) -> None:
        """Local-build should be callable without routing through environment variables."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "Containerfiles").mkdir()
            (repo_root / "Containerfiles" / "Containerfile.dev").write_text(
                "FROM ubuntu:22.04\n",
                encoding="utf-8",
            )
            download_script = repo_root / "scripts" / "build" / "download_tarballs.sh"
            download_script.parent.mkdir(parents=True)
            download_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            download_script.chmod(download_script.stat().st_mode | stat.S_IXUSR)

            request = orchestration.LocalBuildRequest(
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
                download_script=str(download_script),
            )
            download_result = subprocess.CompletedProcess(args=[str(download_script)], returncode=0)
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
                with patch.object(orchestration, "detect_container_engine", return_value="docker"):
                    with patch.object(
                        orchestration,
                        "_run_command",
                        side_effect=[download_result, build_result, inspect_result, inspect_result],
                    ):
                        result = orchestration.local_build(request)

        self.assertEqual(result.container_type, "dev")
        self.assertEqual(
            result.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/sst-dev:latest-{self.host_arch}",
        )
        self.assertEqual(result.image_size_mb, 256)

    def test_local_build_shim_completes_metadata_dev_build_with_fake_engine(self) -> None:
        """The local-build shell entrypoint should dispatch into the Python-backed build path."""

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_download_script = Path(temp_dir) / "download_tarballs.sh"
            fake_download_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_download_script.chmod(fake_download_script.stat().st_mode | stat.S_IXUSR)

            fake_engine = Path(temp_dir) / "docker"
            fake_engine.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "command=${1:?}\n"
                "shift\n"
                "case \"$command\" in\n"
                "  version)\n"
                "    exit 0\n"
                "    ;;\n"
                "  info)\n"
                "    exit 0\n"
                "    ;;\n"
                "  build)\n"
                "    exit 0\n"
                "    ;;\n"
                "  image)\n"
                "    subcommand=${1:?}\n"
                "    shift\n"
                "    if [ \"$subcommand\" = \"inspect\" ]; then\n"
                "      printf '[{\"Size\":268435456,\"Architecture\":\"amd64\",\"Config\":{\"Env\":[\"PATH=/opt/sst/bin:/opt/mpi/bin\"]},\"RootFS\":{\"Layers\":[\"sha256:abc\"]}}]'\n"
                "      exit 0\n"
                "    fi\n"
                "    exit 1\n"
                "    ;;\n"
                "  rmi)\n"
                "    exit 0\n"
                "    ;;\n"
                "  builder)\n"
                "    subcommand=${1:?}\n"
                "    shift\n"
                "    if [ \"$subcommand\" = \"prune\" ]; then\n"
                "      exit 0\n"
                "    fi\n"
                "    exit 1\n"
                "    ;;\n"
                "esac\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_engine.chmod(fake_engine.stat().st_mode | stat.S_IXUSR)

            result = self._run_shim(
                "scripts/build/local-build.sh",
                {
                    "PATH": f"{temp_dir}:{os.environ.get('PATH', '')}",
                    "DOWNLOAD_SCRIPT": str(fake_download_script),
                },
                ["dev", "--validation", "metadata", "--cleanup"],
            )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Build sequence completed successfully!", result.stdout)

    def test_download_tarballs_shim_dispatches_to_python_cli(self) -> None:
        """The download shell entrypoint should preserve the existing CLI contract."""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            download_dir = temp_path / "downloads"
            download_dir.mkdir()

            mpich_source = temp_path / "mpich-source.tar.gz"
            core_source = temp_path / "sstcore-source.tar.gz"
            elements_source = temp_path / "sstelements-source.tar.gz"
            mpich_source.write_bytes(b"shim-mpich-source")
            core_source.write_bytes(b"shim-sst-core-source")
            elements_source.write_bytes(b"shim-sst-elements-source")

            result = self._run_shim(
                "scripts/build/download_tarballs.sh",
                {
                    "SST_DOWNLOAD_MPICH_URL": mpich_source.resolve().as_uri(),
                    "SST_DOWNLOAD_CORE_URL": core_source.resolve().as_uri(),
                    "SST_DOWNLOAD_ELEMENTS_URL": elements_source.resolve().as_uri(),
                },
                [
                    "--sst-version",
                    "15.1.2",
                    "--sst-elements-version",
                    "15.1.0",
                    "--mpich-version",
                    "4.0.2",
                    "--force",
                ],
                cwd=download_dir,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("All requested files downloaded successfully!", result.stdout)
            self.assertEqual((download_dir / "mpich-4.0.2.tar.gz").read_bytes(), b"shim-mpich-source")
            self.assertEqual(
                (download_dir / "sstcore-15.1.2.tar.gz").read_bytes(),
                b"shim-sst-core-source",
            )
            self.assertEqual(
                (download_dir / "sstelements-15.1.0.tar.gz").read_bytes(),
                b"shim-sst-elements-source",
            )

    def test_plan_standard_local_build_spec_captures_release_inputs(self) -> None:
        """Standard local builds should produce a reusable build spec."""

        request = orchestration.LocalBuildRequest(
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

        spec = orchestration.plan_local_build_spec(request)

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

    def test_plan_custom_build_spec_captures_full_build_from_local_checkout(self) -> None:
        """Custom build planning should encode repository sources and build arguments."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "sst-core"
            source_dir.mkdir()
            (source_dir / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source_dir / "configure.ac").write_text("AC_INIT([sst-core],[test])\n", encoding="utf-8")

            request = orchestration.CustomBuildRequest(
                target_platform=self.host_platform,
                tag_suffix="local-main-full",
                sst_core_path=str(source_dir),
                sst_elements_repo="https://github.com/sstsimulator/sst-elements.git",
                sst_elements_ref="main",
                enable_perf_tracking=True,
                validation_mode="metadata",
                registry="ghcr.io/hpc-ai-adv-dev",
            )

            spec = orchestration.plan_custom_build_spec(request)

        self.assertEqual(spec.build_kind, "custom")
        self.assertEqual(spec.source.source_kind, "local-checkout")
        self.assertTrue(spec.source.uses_local_core_checkout)
        self.assertEqual(spec.primary_platform_build.build_target, "full-build")
        self.assertIn("LOCAL_SST_CORE=1", spec.primary_platform_build.build_args)
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

    def test_plan_experiment_build_spec_resolves_template_build(self) -> None:
        """Experiment planning should capture template Containerfile builds and base images."""

        request = orchestration.ExperimentBuildRequest(
            experiment_name="phold-example",
            base_image="sst-core:latest",
            build_platforms=self.host_platform,
            registry="ghcr.io/hpc-ai-adv-dev",
            tag_suffix="latest",
            validation_mode="metadata",
            build_args=("EXTRA=1",),
        )

        spec = orchestration.plan_experiment_build_spec(
            request,
            validate_base_image=False,
        )

        self.assertEqual(spec.build_kind, "experiment")
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
        self.assertIn("EXTRA=1", spec.primary_platform_build.build_args)
        self.assertIn(
            f"BASE_IMAGE=ghcr.io/{os.environ.get('USER', '')}/sst-core:latest",
            spec.primary_platform_build.build_args,
        )
        self.assertEqual(
            spec.primary_platform_build.image_tag,
            f"ghcr.io/hpc-ai-adv-dev/phold-example:latest-{self.host_arch}",
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
        self.assertEqual(
            spec.primary_platform_build.additional_contexts,
            (
                f"sst_core_input={self.repo_root / 'Containerfiles' / 'empty-contexts' / 'sst-core'}",
            ),
        )
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

    def test_plan_workflow_bake_emits_named_context_for_git_ref_builds(self) -> None:
        """Git-ref workflow builds should consume the tracked empty SST-core context."""

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
        contexts_map = cast(dict[str, str], amd64_target["contexts"])

        self.assertEqual(
            contexts_map,
            {"sst_core_input": "Containerfiles/empty-contexts/sst-core"},
        )

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

        self.assertEqual(amd64_target["context"], "phold-example")
        self.assertEqual(
            amd64_target["dockerfile"],
            str(self.repo_root / "Containerfiles" / "Containerfile.experiment"),
        )

    def test_prepare_workflow_build_shim_emits_latest_alias_output(self) -> None:
        """The workflow planner shim should expose latest aliases for release-style requests."""

        with tempfile.NamedTemporaryFile() as output_file:
            result = self._run_shim(
                "scripts/orchestration/prepare-workflow-build.sh",
                {
                    "CONTAINER_TYPE": "core",
                    "IMAGE_PREFIX": "hpc-ai-adv-dev/sst",
                    "BUILD_PLATFORMS": "linux/amd64,linux/arm64",
                    "TAG_SUFFIX": "15.1.2",
                    "REGISTRY": "ghcr.io",
                    "SST_VERSION": "15.1.2",
                    "TAG_AS_LATEST": "true",
                    "GITHUB_OUTPUT": output_file.name,
                },
            )

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("resolved_tag_suffix=15.1.2", written)
        alias_tags_line = next(
            line for line in written.splitlines() if line.startswith("alias_tags_json=")
        )
        self.assertEqual(
            json.loads(alias_tags_line.split("=", 1)[1]),
            ["ghcr.io/hpc-ai-adv-dev/sst-core:latest"],
        )

    def test_prepare_workflow_build_shim_emits_master_latest_alias_output(self) -> None:
        """The workflow planner shim should expose master-latest aliases for nightly-style requests."""

        with tempfile.NamedTemporaryFile() as output_file:
            result = self._run_shim(
                "scripts/orchestration/prepare-workflow-build.sh",
                {
                    "CONTAINER_TYPE": "core",
                    "IMAGE_PREFIX": "hpc-ai-adv-dev/sst",
                    "BUILD_PLATFORMS": "linux/amd64,linux/arm64",
                    "TAG_SUFFIX": "master-abc1234",
                    "REGISTRY": "ghcr.io",
                    "SST_CORE_REPO": "https://github.com/sstsimulator/sst-core.git",
                    "SST_CORE_REF": "abc1234",
                    "PUBLISH_MASTER_LATEST": "true",
                    "GITHUB_OUTPUT": output_file.name,
                },
            )

            written = Path(output_file.name).read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("resolved_tag_suffix=master-abc1234", written)
        alias_tags_line = next(
            line for line in written.splitlines() if line.startswith("alias_tags_json=")
        )
        self.assertEqual(
            json.loads(alias_tags_line.split("=", 1)[1]),
            ["ghcr.io/hpc-ai-adv-dev/sst-core:master-latest"],
        )


if __name__ == "__main__":
    unittest.main()