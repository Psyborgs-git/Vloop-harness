import os
import tarfile
import io

def test_path_traversal_detection():
    base_dir = os.path.abspath("/tmp/workspaces")

    # Test 1: Workspace ID traversal
    request_task_id = "../../../../etc"
    workspace_dir = os.path.abspath(os.path.join(base_dir, request_task_id))

    # Validation logic check
    assert os.path.commonpath([base_dir, workspace_dir]) != base_dir, "Path traversal should be detected"

    # Test 2: Sibling path bypass (startswith vulnerability)
    request_task_id = "../workspaces-hacked"
    workspace_dir = os.path.abspath(os.path.join(base_dir, request_task_id))

    assert os.path.commonpath([base_dir, workspace_dir]) != base_dir, "Sibling path traversal should be detected"

    # Test 3: Tarball Zip Slip traversal
    workspace_dir = os.path.abspath(os.path.join(base_dir, "valid_task"))

    f = io.BytesIO()
    with tarfile.open(fileobj=f, mode='w') as tar:
        info = tarfile.TarInfo(name="../../../../etc/passwd")
        info.size = 11
        tar.addfile(info, io.BytesIO(b"hello world"))

    f.seek(0)
    tar_file = f.read()

    detected = False
    with tarfile.open(fileobj=io.BytesIO(tar_file)) as tar:
        for member in tar.getmembers():
            member_path = os.path.abspath(os.path.join(workspace_dir, member.name))
            if os.path.commonpath([workspace_dir, member_path]) != workspace_dir:
                detected = True
                break

    assert detected, "Path traversal in tarball member should be detected"
