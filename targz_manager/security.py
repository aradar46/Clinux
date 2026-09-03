"""
Clinux Security Auditor Module
Read-only developer-oriented security audit running entirely in user space.
Inspects local configuration, permissions, PATH risks, credentials, network exposure, and services.
"""

import os
import re
import sys
import glob
import time
import shutil
import socket
import datetime
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class SecurityAuditor:
    def __init__(self, home_dir: Optional[Path] = None):
        self.home = (home_dir or Path.home()).resolve()
        self.user = os.environ.get("USER") or os.environ.get("LOGNAME") or self.home.name

    def audit_all(self) -> Dict[str, Any]:
        """Run all security audit checks and return structured results."""
        findings: List[Dict[str, Any]] = []

        findings.extend(self.check_ssh_configuration())
        findings.extend(self.check_path_hijacking())
        findings.extend(self.check_git_and_secrets())
        findings.extend(self.check_env_and_private_keys())
        findings.extend(self.check_network_exposure())
        findings.extend(self.check_container_access())
        findings.extend(self.check_user_services_and_cron())
        findings.extend(self.check_file_permissions_and_symlinks())
        findings.extend(self.check_system_ssh_config())

        summary = {
            "high": sum(1 for f in findings if f["severity"] == "HIGH"),
            "medium": sum(1 for f in findings if f["severity"] == "MEDIUM"),
            "low": sum(1 for f in findings if f["severity"] == "LOW"),
            "passed": sum(1 for f in findings if f["severity"] == "PASSED"),
            "info": sum(1 for f in findings if f["severity"] == "INFO"),
            "total": len(findings)
        }

        return {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": self.user,
            "home": str(self.home),
            "summary": summary,
            "findings": findings
        }

    def check_ssh_configuration(self) -> List[Dict[str, Any]]:
        findings = []
        ssh_dir = self.home / ".ssh"

        if not ssh_dir.exists():
            findings.append({
                "id": "ssh_dir_missing",
                "category": "SSH & Credentials",
                "severity": "PASSED",
                "title": "SSH Directory Not Present",
                "evidence": f"{ssh_dir} does not exist.",
                "risk": "None.",
                "why_it_matters": "No SSH user directory exists to audit.",
                "remediation": None
            })
            return findings

        # Check ~/.ssh directory permissions
        try:
            st = ssh_dir.stat()
            perms = oct(st.st_mode & 0o777)
            if (st.st_mode & 0o077) != 0:
                findings.append({
                    "id": "ssh_dir_permissions",
                    "category": "SSH & Credentials",
                    "severity": "HIGH",
                    "title": "SSH Directory Permissions Too Open",
                    "evidence": f"~/.ssh permissions are {perms} (expected 0700 or 0750)",
                    "risk": "Other local users on this system could view or list your SSH files.",
                    "why_it_matters": "SSH key locations must be protected from local read access.",
                    "remediation": "chmod 700 ~/.ssh"
                })
            else:
                findings.append({
                    "id": "ssh_dir_permissions",
                    "category": "SSH & Credentials",
                    "severity": "PASSED",
                    "title": "SSH Directory Protected",
                    "evidence": f"~/.ssh permissions are {perms}",
                    "risk": "None.",
                    "why_it_matters": "Only owner can access ~/.ssh directory.",
                    "remediation": None
                })
        except Exception as e:
            findings.append({
                "id": "ssh_dir_permissions",
                "category": "SSH & Credentials",
                "severity": "INFO",
                "title": "SSH Directory Inspection Error",
                "evidence": f"Could not stat ~/.ssh: {e}",
                "risk": "Unable to verify directory permissions.",
                "why_it_matters": "Permissions check failed.",
                "remediation": None
            })

        # Check private key permissions
        key_patterns = ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "*.pem", "*.key"]
        private_keys_found = []
        for pat in key_patterns:
            for p in ssh_dir.glob(pat):
                if p.is_file() and not p.name.endswith(".pub"):
                    private_keys_found.append(p)

        for pk in private_keys_found:
            try:
                st = pk.stat()
                perms = oct(st.st_mode & 0o777)
                if (st.st_mode & 0o077) != 0:
                    findings.append({
                        "id": f"ssh_key_perm_{pk.name}",
                        "category": "SSH & Credentials",
                        "severity": "HIGH",
                        "title": f"Private Key Permissions Too Open ({pk.name})",
                        "evidence": f"{pk} permissions: {perms}",
                        "risk": "Group or world readable private key allows unauthorized key copying.",
                        "why_it_matters": "Private SSH keys must strictly be readable only by their owner.",
                        "remediation": f"chmod 600 {pk}"
                    })
                else:
                    findings.append({
                        "id": f"ssh_key_perm_{pk.name}",
                        "category": "SSH & Credentials",
                        "severity": "PASSED",
                        "title": f"Private Key Protected ({pk.name})",
                        "evidence": f"{pk.name} permissions: {perms}",
                        "risk": "None.",
                        "why_it_matters": "Private key is restricted to owner only.",
                        "remediation": None
                    })
            except Exception:
                pass

        # Check authorized_keys permissions
        auth_keys = ssh_dir / "authorized_keys"
        if auth_keys.exists():
            try:
                st = auth_keys.stat()
                perms = oct(st.st_mode & 0o777)
                if (st.st_mode & 0o022) != 0:
                    findings.append({
                        "id": "ssh_auth_keys_writable",
                        "category": "SSH & Credentials",
                        "severity": "HIGH",
                        "title": "authorized_keys Is Group/World Writable",
                        "evidence": f"~/.ssh/authorized_keys permissions: {perms}",
                        "risk": "Other users could insert their public keys and gain unauthorized SSH access.",
                        "why_it_matters": "authorized_keys controls remote authentication into your user account.",
                        "remediation": "chmod 600 ~/.ssh/authorized_keys"
                    })
                else:
                    findings.append({
                        "id": "ssh_auth_keys_writable",
                        "category": "SSH & Credentials",
                        "severity": "PASSED",
                        "title": "authorized_keys Permissions Secure",
                        "evidence": f"~/.ssh/authorized_keys permissions: {perms}",
                        "risk": "None.",
                        "why_it_matters": "authorized_keys is protected from modifications by other users.",
                        "remediation": None
                    })
            except Exception:
                pass

        return findings

    def check_path_hijacking(self) -> List[Dict[str, Any]]:
        findings = []
        raw_path = os.environ.get("PATH", "")
        path_entries = raw_path.split(":")

        system_dirs = {"/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/usr/local/sbin"}
        user_writable_before_system = []
        has_current_dir_in_path = False

        seen_system = False
        for idx, entry in enumerate(path_entries):
            if entry == "" or entry == ".":
                has_current_dir_in_path = True
                continue

            entry_p = Path(entry).resolve()
            if str(entry_p) in system_dirs:
                seen_system = True
                continue

            # Check if directory exists and is user writable
            if entry_p.exists() and entry_p.is_dir():
                try:
                    if os.access(entry_p, os.W_OK) and not seen_system:
                        user_writable_before_system.append((entry, idx))
                except Exception:
                    pass

        if has_current_dir_in_path:
            findings.append({
                "id": "path_current_dir",
                "category": "PATH Hijacking",
                "severity": "HIGH",
                "title": "PATH Contains Current Directory (.)",
                "evidence": "PATH environment variable contains '.' or empty entry.",
                "risk": "Executing a command in an untrusted directory can run malicious local binaries.",
                "why_it_matters": "Relative PATH entries allow attackers to shadow standard utilities like 'ls' or 'git'.",
                "remediation": "Remove '.' or empty entries from $PATH in shell config (~/.bashrc, ~/.zshrc)."
            })

        if user_writable_before_system:
            dirs_str = ", ".join([f"'{d[0]}' (pos {d[1]+1})" for d in user_writable_before_system])
            findings.append({
                "id": "path_user_writable_first",
                "category": "PATH Hijacking",
                "severity": "MEDIUM",
                "title": "User-Writable PATH Directory Precedes System Paths",
                "evidence": f"The following user-writable paths appear before system paths: {dirs_str}",
                "risk": "A locally writable executable in these directories can shadow system commands.",
                "why_it_matters": "If a user-writable binary shadows standard utilities, malware in user space can hijack invocation.",
                "remediation": "Reorder $PATH so /usr/bin precedes custom user directories (~/bin, ~/.local/bin) or ensure custom scripts are strictly owned."
            })
        else:
            findings.append({
                "id": "path_user_writable_first",
                "category": "PATH Hijacking",
                "severity": "PASSED",
                "title": "PATH Order Is Safe",
                "evidence": "No insecure user-writable directories precede system binary directories.",
                "risk": "None.",
                "why_it_matters": "System commands take precedence over custom user binaries.",
                "remediation": None
            })

        return findings

    def check_git_and_secrets(self) -> List[Dict[str, Any]]:
        findings = []

        # Check git credentials file
        git_cred_file = self.home / ".git-credentials"
        if git_cred_file.exists():
            try:
                st = git_cred_file.stat()
                perms = oct(st.st_mode & 0o777)
                if (st.st_mode & 0o077) != 0:
                    findings.append({
                        "id": "git_credentials_exposed",
                        "category": "Developer Security",
                        "severity": "HIGH",
                        "title": "Git Plaintext Credentials Exposed",
                        "evidence": f"{git_cred_file} exists with permissions: {perms}",
                        "risk": "Plaintext Git tokens or passwords can be read by other local users.",
                        "why_it_matters": "Git credentials grant push/pull access to remote code repositories.",
                        "remediation": f"chmod 600 {git_cred_file}"
                    })
                else:
                    findings.append({
                        "id": "git_credentials_exposed",
                        "category": "Developer Security",
                        "severity": "PASSED",
                        "title": "Git Credentials Protected",
                        "evidence": f"{git_cred_file} permissions: {perms}",
                        "risk": "None.",
                        "why_it_matters": "Git credentials file is restricted to user only.",
                        "remediation": None
                    })
            except Exception:
                pass
        else:
            findings.append({
                "id": "git_credentials_exposed",
                "category": "Developer Security",
                "severity": "PASSED",
                "title": "No Plaintext Git Credentials File Found",
                "evidence": "~/.git-credentials file does not exist.",
                "risk": "None.",
                "why_it_matters": "No unencrypted git credentials stored on disk in default location.",
                "remediation": None
            })

        # Check .gitconfig for inline credentials or store helper
        gitconfig = self.home / ".gitconfig"
        if gitconfig.exists():
            try:
                content = gitconfig.read_text(errors="ignore")
                if "helper = store" in content:
                    findings.append({
                        "id": "git_credential_helper_store",
                        "category": "Developer Security",
                        "severity": "LOW",
                        "title": "Git Uses Unencrypted 'store' Credential Helper",
                        "evidence": "~/.gitconfig contains 'helper = store'",
                        "risk": "Git credentials saved on disk in plaintext (~/.git-credentials).",
                        "why_it_matters": "Plaintext credential helpers are vulnerable if backup or disk storage is leaked.",
                        "remediation": "Consider using 'git-credential-libsecret' or SSH key authentication instead."
                    })
            except Exception:
                pass

        return findings

    def check_env_and_private_keys(self) -> List[Dict[str, Any]]:
        findings = []

        # Common developer locations to check for .env files and floating private keys
        search_dirs = [
            self.home,
            self.home / "projects",
            self.home / "src",
            self.home / "code",
            self.home / "workspace",
            self.home / "dev",
            self.home / "Downloads",
            self.home / "Desktop",
            Path.cwd()
        ]

        existing_search_dirs = [d for d in set(search_dirs) if d.exists() and d.is_dir()]

        secret_patterns = [
            re.compile(r'(?i)(AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)\s*=\s*[\'"]?([A-Za-z0-9/+=]{16,})[\'"]?'),
            re.compile(r'(?i)(API_KEY|SECRET_KEY|AUTH_TOKEN|PRIVATE_KEY|DATABASE_URL|PASSWORD)\s*=\s*[\'"]?([^\s#\'"]{8,})[\'"]?'),
            re.compile(r'(?i)BEGIN\s+(RSA|EC|OPENSSH|DSA|PRIVATE)\s+KEY')
        ]

        found_env_files = []
        found_floating_keys = []
        env_with_secrets = []

        for base_dir in existing_search_dirs:
            # Look for .env files up to depth 3
            try:
                for root, dirs, files in os.walk(base_dir):
                    # Limit depth
                    try:
                        rel_parts = Path(root).relative_to(base_dir).parts
                        if len(rel_parts) > 2:
                            dirs.clear()
                            continue
                    except Exception:
                        pass

                    # Ignore node_modules, .git, venv
                    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.venv', 'venv', '__pycache__', '.cache')]

                    for file_name in files:
                        file_p = Path(root) / file_name
                        if file_name.endswith(".env") or file_name == ".env" or file_name.startswith(".env."):
                            if file_p not in found_env_files:
                                found_env_files.append(file_p)
                                # Check file contents for potential secrets
                                try:
                                    txt = file_p.read_text(errors="ignore")
                                    for pat in secret_patterns:
                                        if pat.search(txt):
                                            env_with_secrets.append(file_p)
                                            break
                                except Exception:
                                    pass

                        elif file_name.endswith(".pem") or (file_name.endswith(".key") and "ssh" not in str(file_p)):
                            if file_p not in found_floating_keys:
                                found_floating_keys.append(file_p)
            except Exception:
                pass

        if env_with_secrets:
            envs_str = ", ".join(str(p.relative_to(self.home) if p.is_relative_to(self.home) else p) for p in env_with_secrets[:5])
            findings.append({
                "id": "env_file_secrets",
                "category": "Secrets & Credentials",
                "severity": "HIGH",
                "title": "Secrets / API Keys Detected in .env Files",
                "evidence": f"Potential API keys or secrets detected in: {envs_str}",
                "risk": "Accidental commit or unencrypted storage of API keys can lead to cloud resources takeover.",
                "why_it_matters": ".env files must be added to .gitignore and kept out of version control.",
                "remediation": "Ensure .env is in .gitignore, restrict permissions (chmod 600), or use secret manager."
            })
        elif found_env_files:
            envs_str = ", ".join(str(p.relative_to(self.home) if p.is_relative_to(self.home) else p) for p in found_env_files[:5])
            findings.append({
                "id": "env_file_detected",
                "category": "Secrets & Credentials",
                "severity": "LOW",
                "title": ".env Configuration File Found in Workspace",
                "evidence": f"Found .env file(s) in repository paths: {envs_str}",
                "risk": "Risk of accidentally committing credentials to source control.",
                "why_it_matters": "Verify .env files are in .gitignore.",
                "remediation": "Confirm .env is listed in project .gitignore."
            })
        else:
            findings.append({
                "id": "env_file_detected",
                "category": "Secrets & Credentials",
                "severity": "PASSED",
                "title": "No Unprotected Secrets or Floating Keys Detected",
                "evidence": "No exposed .env files with secrets found in developer workspaces.",
                "risk": "None.",
                "why_it_matters": "Developer workspace is free of exposed plaintext environment secrets.",
                "remediation": None
            })

        if found_floating_keys:
            keys_str = ", ".join(str(p.relative_to(self.home) if p.is_relative_to(self.home) else p) for p in found_floating_keys[:5])
            findings.append({
                "id": "floating_private_keys",
                "category": "Secrets & Credentials",
                "severity": "MEDIUM",
                "title": "Private Key Files Found Outside ~/.ssh",
                "evidence": f"Floating key file(s) found in user directories: {keys_str}",
                "risk": "Private key files in Downloads or Desktop are easily readable and exposed to backup syncs.",
                "why_it_matters": "Keys should be kept in ~/.ssh with restricted permissions.",
                "remediation": "Move private keys to ~/.ssh/ and run chmod 600 on them."
            })

        return findings

    def check_network_exposure(self) -> List[Dict[str, Any]]:
        findings = []
        listening_ports = self._get_listening_ports()

        public_dev_services = []
        localhost_services = []

        for entry in listening_ports:
            addr = entry["address"]
            port = entry["port"]
            proc = entry["process"]

            if addr in ("0.0.0.0", "::", "*"):
                public_dev_services.append(f"{proc} on {addr}:{port}")
            else:
                localhost_services.append(f"{proc} on {addr}:{port}")

        if public_dev_services:
            services_str = "; ".join(public_dev_services[:6])
            findings.append({
                "id": "network_public_dev_server",
                "category": "Network Exposure",
                "severity": "HIGH",
                "title": "Services Listening on All Interfaces (0.0.0.0)",
                "evidence": f"Listening services on 0.0.0.0 / :: : {services_str}",
                "risk": "Services listening on all interfaces are accessible to anyone on your local network (LAN / Wi-Fi).",
                "why_it_matters": "Development servers (Vite, Python, Node, Flask, Rails) bound to 0.0.0.0 expose local code/APIs externally.",
                "remediation": "Bind development servers to 127.0.0.1 (e.g. host='127.0.0.1' or --host 127.0.0.1)."
            })
        elif localhost_services:
            services_str = "; ".join(localhost_services[:6])
            findings.append({
                "id": "network_public_dev_server",
                "category": "Network Exposure",
                "severity": "PASSED",
                "title": "Listening Ports Bound to Localhost Only",
                "evidence": f"Active services bound strictly to 127.0.0.1: {services_str}",
                "risk": "None from local network.",
                "why_it_matters": "Localhost binding prevents external network access to development servers.",
                "remediation": None
            })
        else:
            findings.append({
                "id": "network_public_dev_server",
                "category": "Network Exposure",
                "severity": "PASSED",
                "title": "No User Processes Listening on Public Ports",
                "evidence": "No active user listening ports detected.",
                "risk": "None.",
                "why_it_matters": "No local user processes exposed.",
                "remediation": None
            })

        return findings

    def _get_listening_ports(self) -> List[Dict[str, Any]]:
        ports = []
        # Try ss command first
        try:
            res = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")[1:]
                for line in lines:
                    if "LISTEN" not in line and "UNCONN" not in line:
                        continue
                    parts = line.split()
                    if len(parts) >= 5:
                        local_addr = parts[4]
                        proc_info = parts[6] if len(parts) > 6 else ""

                        # Parse address and port
                        if ":" in local_addr:
                            addr, port_str = local_addr.rsplit(":", 1)
                            addr = addr.strip("[]")
                            proc_name = "Unknown"
                            if 'users:(("' in proc_info:
                                proc_match = re.search(r'users:\(\("([^"]+)"', proc_info)
                                if proc_match:
                                    proc_name = proc_match.group(1)

                            ports.append({"address": addr, "port": port_str, "process": proc_name})
                return ports
        except Exception:
            pass

        # Fallback to netstat
        try:
            res = subprocess.run(["netstat", "-tuln"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")[2:]
                for line in lines:
                    if "LISTEN" not in line:
                        continue
                    parts = line.split()
                    if len(parts) >= 4:
                        local_addr = parts[3]
                        if ":" in local_addr:
                            addr, port_str = local_addr.rsplit(":", 1)
                            ports.append({"address": addr, "port": port_str, "process": "Service"})
                return ports
        except Exception:
            pass

        return ports

    def check_container_access(self) -> List[Dict[str, Any]]:
        findings = []

        # Docker socket accessibility
        docker_socket = Path("/var/run/docker.sock")
        if docker_socket.exists():
            try:
                if os.access(docker_socket, os.R_OK | os.W_OK):
                    findings.append({
                        "id": "docker_socket_access",
                        "category": "Container & System",
                        "severity": "MEDIUM",
                        "title": "Docker Socket Accessible without Sudo",
                        "evidence": "/var/run/docker.sock is readable and writable by current user.",
                        "risk": "User process can spawn privileged containers and mount root directory (/), granting effectively root level power.",
                        "why_it_matters": "Membership in the 'docker' group is equivalent to passwordless root access.",
                        "remediation": "Be cautious running untrusted code; consider rootless Podman or rootless Docker for isolation."
                    })
                else:
                    findings.append({
                        "id": "docker_socket_access",
                        "category": "Container & System",
                        "severity": "PASSED",
                        "title": "Docker Socket Protected",
                        "evidence": "/var/run/docker.sock requires root/sudo access.",
                        "risk": "None.",
                        "why_it_matters": "Docker daemon cannot be accessed directly by non-privileged user processes.",
                        "remediation": None
                    })
            except Exception:
                pass
        else:
            findings.append({
                "id": "docker_socket_access",
                "category": "Container & System",
                "severity": "PASSED",
                "title": "Docker Socket Not Present",
                "evidence": "/var/run/docker.sock does not exist.",
                "risk": "None.",
                "why_it_matters": "Standard docker daemon socket is not running.",
                "remediation": None
            })

        return findings

    def check_user_services_and_cron(self) -> List[Dict[str, Any]]:
        findings = []

        # Systemd user services
        user_systemd_dir = self.home / ".config" / "systemd" / "user"
        systemd_services = []
        if user_systemd_dir.exists():
            try:
                for f in user_systemd_dir.glob("*.service"):
                    systemd_services.append(f.name)
            except Exception:
                pass

        if systemd_services:
            svc_str = ", ".join(systemd_services[:5])
            findings.append({
                "id": "user_systemd_services",
                "category": "Autostart & Services",
                "severity": "INFO",
                "title": f"User Systemd Services Present ({len(systemd_services)})",
                "evidence": f"Configured user systemd services: {svc_str}",
                "risk": "User services automatically run background code on user login.",
                "why_it_matters": "Audit user-level background daemons periodically.",
                "remediation": None
            })
        else:
            findings.append({
                "id": "user_systemd_services",
                "category": "Autostart & Services",
                "severity": "PASSED",
                "title": "No Custom User Systemd Services",
                "evidence": "~/.config/systemd/user/ is empty or clean.",
                "risk": "None.",
                "why_it_matters": "No hidden background systemd user services configured.",
                "remediation": None
            })

        # User cron jobs
        try:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                cron_lines = [l for l in res.stdout.strip().split("\n") if l and not l.startswith("#")]
                if cron_lines:
                    findings.append({
                        "id": "user_cron_jobs",
                        "category": "Autostart & Services",
                        "severity": "LOW",
                        "title": f"Active User Cron Jobs ({len(cron_lines)})",
                        "evidence": f"Crontab entries found for user '{self.user}'.",
                        "risk": "Scheduled jobs execute automatically in the background.",
                        "why_it_matters": "Ensure scheduled cron jobs are expected and running legitimate maintenance scripts.",
                        "remediation": "Review active jobs with 'crontab -l'."
                    })
                else:
                    findings.append({
                        "id": "user_cron_jobs",
                        "category": "Autostart & Services",
                        "severity": "PASSED",
                        "title": "No User Cron Jobs Configured",
                        "evidence": "User crontab has no active cron directives.",
                        "risk": "None.",
                        "why_it_matters": "No scheduled background jobs.",
                        "remediation": None
                    })
            else:
                findings.append({
                    "id": "user_cron_jobs",
                    "category": "Autostart & Services",
                    "severity": "PASSED",
                    "title": "No User Cron Jobs Configured",
                    "evidence": "No crontab for current user.",
                    "risk": "None.",
                    "why_it_matters": "No scheduled background jobs.",
                    "remediation": None
                })
        except Exception:
            pass

        # Autostart applications
        autostart_dir = self.home / ".config" / "autostart"
        autostart_entries = []
        if autostart_dir.exists():
            try:
                for f in autostart_dir.glob("*.desktop"):
                    autostart_entries.append(f.name)
            except Exception:
                pass

        if autostart_entries:
            entries_str = ", ".join(autostart_entries[:5])
            findings.append({
                "id": "autostart_apps",
                "category": "Autostart & Services",
                "severity": "INFO",
                "title": f"Desktop Autostart Applications ({len(autostart_entries)})",
                "evidence": f"Autostart desktop files: {entries_str}",
                "risk": "Applications launch automatically upon graphical desktop session start.",
                "why_it_matters": "Review autostart applications for performance and unauthorized launch items.",
                "remediation": "Inspect items in ~/.config/autostart/."
            })

        return findings

    def check_file_permissions_and_symlinks(self) -> List[Dict[str, Any]]:
        findings = []

        # Broken symlinks in PATH and bin dirs
        bin_dirs = [self.home / "bin", self.home / ".local" / "bin"]
        broken_links = []

        for bd in bin_dirs:
            if bd.exists():
                try:
                    for item in bd.iterdir():
                        if item.is_symlink() and not item.exists():
                            broken_links.append(item)
                except Exception:
                    pass

        if broken_links:
            links_str = ", ".join([l.name for l in broken_links[:5]])
            findings.append({
                "id": "broken_symlinks",
                "category": "File Hygiene & Integrity",
                "severity": "LOW",
                "title": f"Broken Symlinks in User Bin Directories ({len(broken_links)})",
                "evidence": f"Dangling executable symlinks: {links_str}",
                "risk": "Execution errors or command resolution failure.",
                "why_it_matters": "Dangling symlinks point to removed software or targets.",
                "remediation": f"Remove dangling symlinks in {self.home / '.local' / 'bin'}."
            })
        else:
            findings.append({
                "id": "broken_symlinks",
                "category": "File Hygiene & Integrity",
                "severity": "PASSED",
                "title": "No Broken Symlinks in User Bin Directories",
                "evidence": "All binary symlinks in ~/bin and ~/.local/bin resolve properly.",
                "risk": "None.",
                "why_it_matters": "Binary directory symlinks are clean.",
                "remediation": None
            })

        # Check world-writable sensitive history/gnupg files in $HOME
        sensitive_files = [
            self.home / ".bash_history",
            self.home / ".zsh_history",
            self.home / ".gnupg",
            self.home / ".netrc"
        ]

        for sf in sensitive_files:
            if sf.exists():
                try:
                    st = sf.stat()
                    perms = oct(st.st_mode & 0o777)
                    if (st.st_mode & 0o077) != 0:
                        findings.append({
                            "id": f"perm_{sf.name}",
                            "category": "File Hygiene & Integrity",
                            "severity": "HIGH" if sf.name in (".netrc", ".gnupg") else "MEDIUM",
                            "title": f"Sensitive User File Permissions Too Open ({sf.name})",
                            "evidence": f"{sf} permissions: {perms}",
                            "risk": "Other local users can read shell command history or sensitive tokens.",
                            "why_it_matters": "History and GPG files may contain tokens or sensitive arguments.",
                            "remediation": f"chmod {'700' if sf.is_dir() else '600'} {sf}"
                        })
                except Exception:
                    pass

        return findings

    def check_system_ssh_config(self) -> List[Dict[str, Any]]:
        findings = []
        sshd_config = Path("/etc/ssh/sshd_config")

        if sshd_config.exists():
            try:
                if not os.access(sshd_config, os.R_OK):
                    findings.append({
                        "id": "system_sshd_config",
                        "category": "System Level Inspection",
                        "severity": "INFO",
                        "title": "SSH Server Configuration (/etc/ssh/sshd_config)",
                        "evidence": "Unable to inspect /etc/ssh/sshd_config (insufficient permissions).",
                        "risk": "Cannot inspect root level SSH daemon settings without sudo.",
                        "why_it_matters": "System-level SSH server config dictates password authentication and root login rules.",
                        "remediation": "Run Clinux with elevated privileges (sudo) for system-level daemon audit."
                    })
                else:
                    txt = sshd_config.read_text(errors="ignore")
                    has_root_login = re.search(r'^\s*PermitRootLogin\s+yes', txt, re.MULTILINE)

                    if has_root_login:
                        findings.append({
                            "id": "sshd_permit_root",
                            "category": "System Level Inspection",
                            "severity": "HIGH",
                            "title": "SSH Server Permits Direct Root Login",
                            "evidence": "/etc/ssh/sshd_config specifies 'PermitRootLogin yes'",
                            "risk": "Direct root SSH logins increase risk of brute-force root compromises.",
                            "why_it_matters": "Root login via SSH should be disabled in favor of sudo.",
                            "remediation": "Set 'PermitRootLogin no' in /etc/ssh/sshd_config and restart sshd."
                        })
                    else:
                        findings.append({
                            "id": "sshd_permit_root",
                            "category": "System Level Inspection",
                            "severity": "PASSED",
                            "title": "SSH Root Login Restricted",
                            "evidence": "/etc/ssh/sshd_config does not permit direct root login.",
                            "risk": "None.",
                            "why_it_matters": "Root logins restricted.",
                            "remediation": None
                        })
            except Exception:
                pass
        return findings

    def format_text_report(self, audit_result: Dict[str, Any]) -> str:
        """Generate formatted CLI plain-text security report."""
        summary = audit_result["summary"]
        findings = audit_result["findings"]

        lines = [
            "CLINUX SECURITY AUDIT",
            "────────────────────────────────────────",
            f"User: {audit_result['user']} | Date: {audit_result['timestamp']}",
            "",
            f"[!] {summary['high']} HIGH",
            f"[!] {summary['medium']} MEDIUM",
            f"[~] {summary['low']} LOW",
            f"[i] {summary['info']} INFO",
            f"[✓] {summary['passed']} PASSED",
            ""
        ]

        # Group non-passed findings
        severities_order = ["HIGH", "MEDIUM", "LOW", "INFO"]
        for sev in severities_order:
            sev_findings = [f for f in findings if f["severity"] == sev]
            if not sev_findings:
                continue

            lines.append(sev)
            lines.append("────────────────────────────────────────")
            for f in sev_findings:
                icon = "[!]" if sev in ("HIGH", "MEDIUM") else ("[~]" if sev == "LOW" else "[i]")
                lines.append(f"{icon} {f['title'].upper()}")
                lines.append(f"    {f['evidence']}")
                lines.append("")
                lines.append(f"    Risk: {f['risk']}")
                lines.append(f"    Why:  {f['why_it_matters']}")
                if f.get("remediation"):
                    lines.append("")
                    lines.append("    Suggested:")
                    lines.append(f"    {f['remediation']}")
                lines.append("")

        # Add Passed Section summary
        passed_findings = [f for f in findings if f["severity"] == "PASSED"]
        if passed_findings:
            lines.append("PASSED CHECKS")
            lines.append("────────────────────────────────────────")
            for f in passed_findings:
                lines.append(f"✓ {f['title']}")
            lines.append("")

        lines.append("────────────────────────────────────────")
        lines.append("Note: Clinux operates as a read-only user-space auditor.")
        lines.append("Run elevated system tools for full root-level kernel/hardware audit.")
        lines.append("")

        return "\n".join(lines)

    def export_report(self, audit_result: Dict[str, Any], filepath: Optional[str] = None, format_type: str = "text") -> str:
        """Export report to text file or json file."""
        if not filepath:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            ext = "json" if format_type == "json" else "txt"
            filepath = f"clinux-security-{date_str}.{ext}"

        target_p = Path(filepath).resolve()

        if format_type == "json":
            import json
            content = json.dumps(audit_result, indent=2)
        else:
            content = self.format_text_report(audit_result)

        target_p.write_text(content, encoding="utf-8")
        return str(target_p)
