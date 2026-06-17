
## 2024-05-18 - [Path Traversal & Zip Slip in Archive Extraction]
**Vulnerability:** The application unsafely extracted `.tar` files received from an external node via `tar.extractall` to a user-controlled path (`task_id`), allowing a malicious actor to perform Zip Slip by exploiting directory traversal both through the target folder name and the files inside the tarball itself.
**Learning:** Python's `tarfile` and `zipfile` modules do not automatically prevent path traversal for member files that begin with `..` or `/`. Combined with joining untrusted user input directly using `os.path.join()`, this allowed for arbitrary code execution / system file overwrites.
**Prevention:** Always validate all path destinations before writing or extracting. Compute the absolute path using `os.path.abspath` and verify that the target correctly starts with the intended base directory using `.startswith()`.
