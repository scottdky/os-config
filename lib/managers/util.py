"""Interactive menu helpers for manager selection flows."""

from typing import cast


def get_single_selection(options: list[str], title: str = 'Select operation', addExit: str | bool = 'Exit') -> int | None:
    """Prompt user to select one option from a terminal menu.

    Args:
        options (list[str]): List of options to display.
        title (str): Title for the selection menu.
        addExit (str | bool): Exit option label. Pass a string to customize the label,
            False to disable, or True/'Exit' for standard exit behavior.

    Returns:
        int | None: Selected index from `options`, or None if cancelled/exit chosen.
    """
    menuOptions = options.copy()

    if addExit is True:
        addExit = 'Exit'
    if addExit:
        menuOptions.append(addExit)

    import simple_term_menu
    menuClass = simple_term_menu.TerminalMenu

    menu = menuClass(menuOptions, title=title)
    menuEntryIndex = cast(int | None, menu.show())
    if menuEntryIndex is None:
        return None
    if addExit and menuEntryIndex == len(menuOptions) - 1:
        return None

    return menuEntryIndex


def get_multi_selection(options: list[str], title: str = 'Select operations') -> list[int] | None:
    """Prompt user to select multiple options from a terminal menu.

    Args:
        options (list[str]): List of options to display.
        title (str): Title for the selection menu.

    Returns:
        list[int] | None: Selected indices, or None if cancelled.
    """
    import simple_term_menu
    menuClass = simple_term_menu.TerminalMenu

    menu = menuClass(
        options,
        title=title,
        multi_select=True,
        multi_select_empty_ok=True,
        multi_select_select_on_accept=False,
    )
    selectedIndicesRaw = cast(list[int] | tuple[int, ...] | None, menu.show())
    if selectedIndicesRaw is None:
        return None
    return list(selectedIndicesRaw)
