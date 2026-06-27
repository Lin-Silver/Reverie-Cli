from reverie.tools.text_to_video import TextToVideoTool


def test_ttv_extract_task_info_preserves_video_id_from_id_field():
    tool = TextToVideoTool({"project_root": "."})

    info = tool._extract_task_info(
        {
            "id": "video_abc123",
            "status": "in_progress",
            "progress": 30,
        }
    )

    assert info["video_id"] == "video_abc123"
    assert info["task_id"] == ""
    assert info["status"] == "in_progress"


def test_ttv_extract_task_info_preserves_task_id_from_id_field():
    tool = TextToVideoTool({"project_root": "."})

    info = tool._extract_task_info(
        {
            "id": "task_abc123",
            "status": "queued",
        }
    )

    assert info["video_id"] == ""
    assert info["task_id"] == "task_abc123"
