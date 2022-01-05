"""Functionality for scraping the data from lo1.gliwice.pl website to retrieve lesson substitution details."""

# Standard library imports
import json
import re
import datetime

# Third-party imports
import lxml.html

# Local application imports
from .. import web
from ... import Colour, file_manager, util


sub_info_pattern = re.compile(
    r"(I+)([A-Z]+)([pg]?)(?:(?:\sgr.\s|,\s|\si\s)p. [^,\s]+)*\s(.*)")
sub_groups_pattern = re.compile(r"(?:\sgr.\s|,\s|\si\s)(p. [^,\s]+)")

source_url = "http://www.lo1.gliwice.pl/zastepstwa-2/"


def parse_html(html: str) -> dict:
    """Parses the HTML and finds a specific hard-coded table, then collects the timetable data from it.

    Arguments:
        html -- a string containing whole HTML code, eg. from the contents of a web request's response.

    Returns a dictionary.
    """
    root: lxml.html.Element = lxml.html.fromstring(html)
    post_xpath: str = "//div[@id='content']/div"
    try:
        post_elem: lxml.html.Element = root.xpath(post_xpath)[0]
    except Exception as e:
        return {"error": util.format_exception_info(e)}
    subs_data = {"post": dict(post_elem.attrib), "lessons": {}}
    lesson_list: dict[int, dict[str, list]] = subs_data["lessons"]

    tables = []

    def extract_data(elem: lxml.html.Element, elem_index: int):
        """Extract the relevant information from each element in the post. Adds result to the subs_data dictionary."""
        if elem.tag == "table":
            tables[-1]["rows"] = len(elem[0])
            return
        if elem.tag != "p":
            # Skip non-paragraph elements (i.e. comments, divs etc.)
            return
        if elem.text == "&nbsp;":
            # Skip blank 'p' elements
            return
        try:
            # Check if this element has children
            child_elem = elem[0]
        except IndexError:
            # The current element has no children
            subs_text: str = elem.text
            if subs_text.endswith(" są odwołane."):
                subs_data["cancelled"] = subs_text
                return
            separator = " - " if " - " in subs_text else " – "
            lessons, info = subs_text.split(separator, maxsplit=1)
            lesson_ints = []
            for lesson in lessons.rstrip('l').split(','):
                if "-" in lesson:
                    start, end = [int(elem_index)
                                  for elem_index in lesson.split('-')]
                    lesson_ints += list(range(start, end + 1))
                else:
                    lesson_ints.append(int(lesson))
            for lesson in lesson_ints:
                info_match = re.match(sub_info_pattern, info)
                groups = re.findall(sub_groups_pattern, info)
                class_year, classes, class_info, details = info_match.groups()
                lesson_list.setdefault(lesson, {})
                for class_letter in classes:
                    class_name = f"{class_year}{class_letter}{class_info or ''}"
                    lesson_list[lesson].setdefault(class_name, [])
                    substitution_info = {}
                    if groups:
                        substitution_info["groups"] = groups
                    substitution_info["details"] = details
                    lesson_list[lesson][class_name].append(substitution_info)
        else:
            # The current element does have children
            if child_elem.tag != "strong":
                return
            if elem_index == 0:
                date_string = child_elem[0].text.split(' ', maxsplit=1)[1]
                date = datetime.datetime.strptime(date_string, "%d.%m.%Y")
                subs_data["date"] = str(date.date())
                return
            if elem_index == 1:
                teachers = child_elem.text.split(', ')
                subs_data["teachers"] = teachers
                return
            if elem_index == 2:
                subs_data["misc"] = child_elem.text
                return
            if not (child_elem.text and child_elem.text.strip()):
                # Skip blank child elements
                return
            tables.append({"heading": child_elem.text})

    for i, p_elem in enumerate(post_elem):
        try:
            # Attempt to extract the relevant data using a hard-coded algorithm
            extract_data(p_elem, i)
        except Exception as e:
            # Page structure has changed, return the nature of the error.
            subs_data["error"] = util.format_exception_info(e)
            break

    # Add the list of tables to the data
    subs_data["tables"] = tables

    # Return dictionary with substitution data
    return subs_data


def get_substitutions(force_update: bool = False) -> tuple[dict, bool]:
    """Gets the current lesson substitutions.
    Returns the data itself and a tuple containing a boolean indicating if the cache already existed.

    Arguments:
        force_update -- a boolean indicating if the cache should be forcefully updated.
    """
    def update_cache_callback() -> dict:
        html: str = web.get_html(source_url, force_update)
        return parse_html(html)
    return file_manager.get_cache("subs", force_update, update_cache_callback)


if __name__ == "__main__":
    colours = vars(Colour)
    for col in colours:
        if not col.startswith('_') and col is not None:
            print(f"Colour {colours[col]}{col}{Colour.ENDC}")
    print()
    try:
        subs: dict = get_substitutions(force_update=True)
        plan = json.dumps(subs, indent=2, ensure_ascii=False)
        print(f"{Colour.OKGREEN}Substitutions:\n{Colour.ENDC}{plan}")
    except KeyboardInterrupt:
        print(f"...{Colour.FAIL}\nGoodbye!\n{Colour.ENDC}")
