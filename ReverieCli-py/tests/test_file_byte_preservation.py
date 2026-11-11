import pytest
from reverie.tools.create_file import CreateFileTool
from reverie.tools.file_ops import FileOpsTool
from reverie.tools.str_replace_editor import StrReplaceEditorTool


@pytest.mark.parametrize('content',['AiO VERIFIED 中文\n','original\r\ntext\r\n','mixed\r\nLF\n'])
def test_native_create_and_read_preserve_exact_newline_bytes(tmp_path,content):
    context={'project_root':tmp_path}
    assert CreateFileTool(context).execute(path='proof.txt',content=content).success
    assert (tmp_path/'proof.txt').read_bytes()==content.encode('utf-8')
    assert FileOpsTool(context).execute(operation='read',path='proof.txt').output==content


def test_exact_replacement_preserves_unrelated_line_endings(tmp_path):
    (tmp_path/'proof.txt').write_bytes(b'first\r\nsecond\nthird\r\n')
    result=StrReplaceEditorTool({'project_root':tmp_path}).execute(command='str_replace',path='proof.txt',old_str='second',new_str='changed')
    assert result.success
    assert (tmp_path/'proof.txt').read_bytes()==b'first\r\nchanged\nthird\r\n'
