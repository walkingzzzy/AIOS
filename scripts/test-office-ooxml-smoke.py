#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "office" / "runtime" / "office_provider.py"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "office-ooxml-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS office OOXML local smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep generated fixtures on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for generated fixtures and audit logs")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_json_command(*args: str, check: bool = True, env: dict[str, str] | None = None) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(RUNTIME), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=command_env,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {sys.executable} {RUNTIME} {' '.join(args)}\n"
            f"{completed.stderr.strip()}\n{completed.stdout.strip()}"
        )
    return completed.returncode, json.loads(completed.stdout)


def write_docx(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>AIOS Office OOXML</w:t></w:r></w:p>
    <w:p><w:r><w:t>Tier 1 bring-up evidence closed.</w:t></w:r></w:p>
    <w:p><w:r><w:t>Rollback rehearsal passed.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""",
        )
        archive.writestr("word/document.xml", document_xml)


def write_xlsx(path: Path) -> None:
    workbook_xml = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Summary" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    sheet_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Quarter</t></is></c><c r="B1" t="inlineStr"><is><t>Amount</t></is></c></row>
    <row r="2"><c r="A2" t="inlineStr"><is><t>2026Q1</t></is></c><c r="B2"><v>128</v></c></row>
  </sheetData>
</worksheet>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""",
        )
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def write_pptx(path: Path) -> None:
    slide_xml = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>AIOS Platform Review</a:t></a:r></a:p>
          <a:p><a:r><a:t>Bring-up closed with recovery evidence.</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>
""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
""",
        )
        archive.writestr(
            "ppt/presentation.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>
""",
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
""",
        )
        archive.writestr("ppt/slides/slide1.xml", slide_xml)


def main() -> int:
    args = parse_args()
    if args.output_dir is not None:
        temp_root = args.output_dir
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        if DEFAULT_WORK_ROOT.exists():
            shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
        DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
        temp_root = DEFAULT_WORK_ROOT

    failed = False
    try:
        audit_log = temp_root / "office-ooxml-audit.jsonl"
        env = dict(os.environ)
        env["AIOS_COMPAT_OFFICE_AUDIT_LOG"] = str(audit_log)

        docx_path = temp_root / "sample.docx"
        xlsx_path = temp_root / "sample.xlsx"
        pptx_path = temp_root / "sample.pptx"
        broken_docx_path = temp_root / "broken.docx"
        unsupported_path = temp_root / "sample.bin"
        write_docx(docx_path)
        write_xlsx(xlsx_path)
        write_pptx(pptx_path)
        broken_docx_path.write_text("not a zip archive", encoding="utf-8")
        unsupported_path.write_text("raw data", encoding="utf-8")

        _, health = run_json_command("health", env=env)
        supported_suffixes = set(health.get("supported_suffixes") or [])
        require({".docx", ".xlsx", ".pptx"}.issubset(supported_suffixes), "health supported_suffixes missing OOXML entries")

        _, docx_payload = run_json_command("open", "--path", str(docx_path), env=env)
        require(docx_payload["status"] == "ok", "docx open should succeed")
        require(docx_payload["title"] == "AIOS Office OOXML", "docx title mismatch")
        require("Rollback rehearsal passed." in docx_payload["preview"], "docx preview mismatch")
        require(docx_payload["mime_type"].endswith("wordprocessingml.document"), "docx mime_type mismatch")

        docx_pdf = temp_root / "sample-docx.pdf"
        _, docx_export = run_json_command("export-pdf", "--path", str(docx_path), "--output-path", str(docx_pdf), env=env)
        require(docx_pdf.exists(), "docx pdf output missing")
        require(docx_pdf.read_bytes().startswith(b"%PDF-1.4"), "docx pdf header mismatch")
        require(docx_export["bytes_written"] == docx_pdf.stat().st_size, "docx bytes_written mismatch")

        _, xlsx_payload = run_json_command("open", "--path", str(xlsx_path), env=env)
        require(xlsx_payload["status"] == "ok", "xlsx open should succeed")
        require(xlsx_payload["title"] == "Summary", "xlsx title mismatch")
        require("Quarter" in xlsx_payload["preview"], "xlsx preview header missing")
        require("2026Q1" in xlsx_payload["preview"], "xlsx preview row missing")
        require(xlsx_payload["mime_type"].endswith("spreadsheetml.sheet"), "xlsx mime_type mismatch")

        xlsx_pdf = temp_root / "sample-xlsx.pdf"
        _, xlsx_export = run_json_command("export-pdf", "--path", str(xlsx_path), "--output-path", str(xlsx_pdf), env=env)
        require(xlsx_pdf.exists(), "xlsx pdf output missing")
        require(xlsx_export["page_count"] >= 1, "xlsx pdf page_count mismatch")

        _, pptx_payload = run_json_command("open", "--path", str(pptx_path), env=env)
        require(pptx_payload["status"] == "ok", "pptx open should succeed")
        require(pptx_payload["title"] == "AIOS Platform Review", "pptx title mismatch")
        require("Bring-up closed with recovery evidence." in pptx_payload["preview"], "pptx preview mismatch")
        require(pptx_payload["mime_type"].endswith("presentationml.presentation"), "pptx mime_type mismatch")

        pptx_pdf = temp_root / "sample-pptx.pdf"
        _, pptx_export = run_json_command("export-pdf", "--path", str(pptx_path), "--output-path", str(pptx_pdf), env=env)
        require(pptx_pdf.exists(), "pptx pdf output missing")
        require(pptx_export["page_count"] >= 1, "pptx pdf page_count mismatch")

        broken_code, broken_payload = run_json_command("open", "--path", str(broken_docx_path), env=env, check=False)
        require(broken_code == 2, f"broken docx should exit 2, got {broken_code}")
        require((broken_payload.get("error") or {}).get("error_code") == "office_document_parse_failed", "broken docx error code mismatch")

        unsupported_code, unsupported_payload = run_json_command("open", "--path", str(unsupported_path), env=env, check=False)
        require(unsupported_code == 2, f"unsupported type should exit 2, got {unsupported_code}")
        require((unsupported_payload.get("error") or {}).get("error_code") == "office_document_type_unsupported", "unsupported type error code mismatch")

        require(audit_log.exists(), "OOXML smoke should produce audit log")
        audit_entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(audit_entries) >= 8, "OOXML smoke audit log entry count mismatch")
        require(any((entry.get("result") or {}).get("error_code") == "office_document_parse_failed" for entry in audit_entries), "audit log missing parse failure entry")
        require(any((entry.get("result") or {}).get("error_code") == "office_document_type_unsupported" for entry in audit_entries), "audit log missing unsupported-type entry")

        print(
            json.dumps(
                {
                    "provider_id": health["provider_id"],
                    "supported_suffixes": sorted(supported_suffixes),
                    "docx_title": docx_payload["title"],
                    "xlsx_title": xlsx_payload["title"],
                    "pptx_title": pptx_payload["title"],
                    "docx_pdf_bytes": docx_export["bytes_written"],
                    "xlsx_pdf_bytes": xlsx_export["bytes_written"],
                    "pptx_pdf_bytes": pptx_export["bytes_written"],
                    "audit_log": str(audit_log),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception:
        failed = True
        raise
    finally:
        preserve_state = failed or args.keep_state or args.output_dir is not None
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
