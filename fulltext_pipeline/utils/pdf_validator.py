"""
PDF 文件基础校验工具。

本模块只校验已经下载到本地的文件，不发送网络请求。

当前负责：
1. 检查文件是否存在；
2. 检查文件大小是否合理；
3. 检查文件头是否为 %PDF-；
4. 计算 SHA256；
5. 返回统一的校验结果。

注意：
这里只进行文件级基础校验。
“PDF 首页标题是否与数据库标题一致”等内容级校验，后续单独实现。
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path


PDF_MAGIC_HEADER = b"%PDF-"
DEFAULT_MIN_PDF_SIZE_BYTES = 1024
DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class PDFValidationResult:
    """
    PDF 文件校验结果。
    """

    valid: bool
    path: str
    size_bytes: int
    sha256: str
    error: str

    def to_dict(self) -> dict:
        """转换为普通字典，便于后续日志记录或数据库回写。"""

        return asdict(self)


def compute_file_sha256(
    file_path: str | Path,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> str:
    """
    分块计算文件 SHA256。

    分块读取可以避免一次性把较大的 PDF 全部加载进内存。
    """

    path = Path(file_path)
    hash_object = sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            hash_object.update(chunk)

    return hash_object.hexdigest()


def validate_pdf_file(
    file_path: str | Path,
    min_size_bytes: int = DEFAULT_MIN_PDF_SIZE_BYTES,
) -> PDFValidationResult:
    """
    对本地 PDF 进行基础校验。

    校验规则：
    1. 路径必须存在；
    2. 路径必须是普通文件；
    3. 文件不能小于 min_size_bytes；
    4. 文件开头必须是 %PDF-；
    5. 文件必须能够完整读取并计算 SHA256。

    校验失败时不会抛出普通文件异常，而是通过 error 返回原因。
    """

    path = Path(file_path)

    if min_size_bytes < 0:
        raise ValueError("min_size_bytes 不能小于 0")

    if not path.exists():
        return PDFValidationResult(
            valid=False,
            path=str(path),
            size_bytes=0,
            sha256="",
            error="file_not_found",
        )

    if not path.is_file():
        return PDFValidationResult(
            valid=False,
            path=str(path),
            size_bytes=0,
            sha256="",
            error="not_a_file",
        )

    try:
        size_bytes = path.stat().st_size

        if size_bytes < min_size_bytes:
            return PDFValidationResult(
                valid=False,
                path=str(path),
                size_bytes=size_bytes,
                sha256="",
                error=(
                    f"file_too_small: "
                    f"{size_bytes} < {min_size_bytes}"
                ),
            )

        with path.open("rb") as file:
            header = file.read(len(PDF_MAGIC_HEADER))

        if header != PDF_MAGIC_HEADER:
            return PDFValidationResult(
                valid=False,
                path=str(path),
                size_bytes=size_bytes,
                sha256="",
                error="invalid_pdf_header",
            )

        file_sha256 = compute_file_sha256(path)

        return PDFValidationResult(
            valid=True,
            path=str(path),
            size_bytes=size_bytes,
            sha256=file_sha256,
            error="",
        )

    except OSError as error:
        return PDFValidationResult(
            valid=False,
            path=str(path),
            size_bytes=0,
            sha256="",
            error=f"os_error: {error}",
        )