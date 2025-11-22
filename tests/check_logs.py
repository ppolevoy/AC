#!/usr/bin/env python3
"""
check_logs.py - Проверка корректности логирования HAProxy операций
"""

import sys
import re
from pathlib import Path


class LogChecker:
    """Класс для проверки логов оркестратора"""

    def __init__(self, log_file):
        self.log_file = Path(log_file)
        self.errors = []
        self.warnings = []
        self.content = ""

    def read_log(self):
        """Читает содержимое лог файла"""
        if not self.log_file.exists():
            self.errors.append(f"Log file not found: {self.log_file}")
            return False

        try:
            with open(self.log_file, 'r') as f:
                self.content = f.read()
            return True
        except Exception as e:
            self.errors.append(f"Error reading log: {e}")
            return False

    def check_haproxy_format(self):
        """Проверяет формат HAProxy записей"""
        # Проверяем наличие информации о HAProxy
        if "HAProxy" not in self.content:
            self.warnings.append("No HAProxy information found in log")

        # Проверяем explicit mapping информацию
        if re.search(r"explicit:\s*(true|false|True|False)", self.content):
            print("✓ Found explicit mapping information")
        else:
            self.warnings.append("No explicit mapping information found")

        # Проверяем backend информацию
        if "Backend" in self.content or "backend" in self.content:
            print("✓ Found backend information")
        else:
            self.warnings.append("No backend information found")

        # Проверяем расширенный формат
        extended_format = re.findall(r"(\w[\w-]*)::(\w[\w-]*)::(\w[\w-]*)", self.content)
        if extended_format:
            print(f"✓ Found {len(extended_format)} extended format entries")
            for server, app, haproxy in extended_format[:3]:  # Показываем первые 3
                print(f"  - {server}::{app}::{haproxy}")
        else:
            # Проверяем старый формат
            old_format = re.findall(r"(\w[\w-]*)::(\w[\w-]*)", self.content)
            if old_format:
                print(f"✓ Found {len(old_format)} legacy format entries")
            else:
                self.warnings.append("No format entries found")

    def check_drain_ready_operations(self):
        """Проверяет операции DRAIN и READY"""
        drain_count = self.content.count("DRAIN")
        ready_count = self.content.count("READY")

        print(f"✓ DRAIN operations: {drain_count}")
        print(f"✓ READY operations: {ready_count}")

        if drain_count == 0:
            self.warnings.append("No DRAIN operations found")

        if ready_count == 0:
            self.warnings.append("No READY operations found")

        # Проверяем успешность операций
        success_pattern = re.findall(r"SUCCESS", self.content)
        failed_pattern = re.findall(r"FAILED", self.content)

        if success_pattern:
            print(f"✓ Successful operations: {len(success_pattern)}")

        if failed_pattern:
            print(f"✗ Failed operations: {len(failed_pattern)}")
            self.errors.append(f"Found {len(failed_pattern)} failed operations")

    def check_batch_processing(self):
        """Проверяет обработку батчей"""
        batch1_match = re.search(r"Batch 1.*?(\d+) instances", self.content)
        batch2_match = re.search(r"Batch 2.*?(\d+) instances", self.content)

        if batch1_match:
            print(f"✓ Batch 1: {batch1_match.group(1)} instances")
        else:
            self.warnings.append("Batch 1 information not found")

        if batch2_match:
            print(f"✓ Batch 2: {batch2_match.group(1)} instances")
        else:
            self.warnings.append("Batch 2 information not found")

    def check_mapping_statistics(self):
        """Проверяет статистику маппинга"""
        explicitly_mapped = re.search(r"Explicitly mapped:\s*(\d+)", self.content)
        using_fallback = re.search(r"Using fallback:\s*(\d+)", self.content)

        if explicitly_mapped:
            print(f"✓ Explicitly mapped: {explicitly_mapped.group(1)} instances")

        if using_fallback:
            print(f"✓ Using fallback: {using_fallback.group(1)} instances")

    def check_completion_status(self):
        """Проверяет статус завершения"""
        if "STATUS: SUCCESS" in self.content:
            print("✓ Task completed successfully")
        elif "STATUS: FAILED" in self.content:
            self.errors.append("Task failed")
        else:
            self.warnings.append("Completion status not found")

    def generate_report(self):
        """Генерирует отчет о проверке"""
        print("\n" + "=" * 50)
        print("LOG VALIDATION REPORT")
        print("=" * 50)
        print(f"Log file: {self.log_file}")
        if self.log_file.exists():
            print(f"Size: {self.log_file.stat().st_size} bytes")
        print()

        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  ✗ {error}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")
            print()

        if not self.errors:
            print("✅ Log validation PASSED")
            return True
        else:
            print("❌ Log validation FAILED")
            return False


def main():
    """Основная функция"""
    if len(sys.argv) != 2:
        print("Usage: python check_logs.py <log_file>")
        sys.exit(1)

    log_file = sys.argv[1]
    checker = LogChecker(log_file)

    if not checker.read_log():
        print("Failed to read log file")
        sys.exit(1)

    print("Checking HAProxy orchestrator logs...")
    print()

    # Выполняем проверки
    checker.check_haproxy_format()
    checker.check_drain_ready_operations()
    checker.check_batch_processing()
    checker.check_mapping_statistics()
    checker.check_completion_status()

    # Генерируем отчет
    success = checker.generate_report()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
