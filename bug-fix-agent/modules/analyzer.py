from modules.log_parser import parse_log
from modules.code_search import find_source
from modules.file_reader import read_context


def analyze(log_file, workspace):
    """
    Runs the complete analysis pipeline.

    Returns a dictionary containing:
    - crash info
    - source path
    - source snippet
    """

    crash = parse_log(log_file)

    source = find_source(
        workspace,
        crash["file"]
    )

    snippet = read_context(
        source,
        crash["line"]
    )

    return {
        "crash": crash,
        "source": source,
        "snippet": snippet
    }
