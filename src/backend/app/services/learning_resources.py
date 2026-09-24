"""Subset of learning resources for the students to read through as AI can hallinate links

Every URL here must be verified to be a valid link and relevant to the topic periodically.
"""

from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Resource:
    """A learning resource for students to read through."""
    concept: str
    label: str
    url: str
    blurb: str          # A short description of the resource for the AI to paraphrase
    check_prompt: str

CONCEPT_RESOURCES: dict[str, list[Resource]] = {
    "recursion": [
        Resource(
            concept="recursion",
            label="Introduction to Recursion",
            url="https://www.geeksforgeeks.org/dsa/introduction-to-recursion-2/",
            blurb="a function that calls itself, and needs a stopping condition to avoid infinite loops.",
            check_prompt="Can you explain what recursion means in programming?"
        )
    ],
    "functions": [
        Resource(
            concept="functions",
            label="Functions in Python",
            url="https://www.w3schools.com/python/python_functions.asp",
            blurb="a block of code that performs a specific task and can be reused throughout the program.",
            check_prompt="Can you explain what functions are in programming?"
        )
    ],
    "loops": [
        Resource(
            concept="loops",
            label="Loops in Python",
            url="https://www.w3schools.com/python/python_for_loops.asp",
            blurb="a control flow statement that allows code to be executed repeatedly based on a condition.",
            check_prompt="Can you explain what loops are in programming?"
        )
    ],
    "variables": [
        Resource(
            concept="variables",
            label="Variables in Python",
            url="https://www.w3schools.com/python/python_variables.asp",
            blurb="a named location in memory that stores a value which can be changed during program execution.",
            check_prompt="Can you explain what variables are in programming?"
        )
    ],
    "data_structures": [
        Resource(
            concept="data_structures",
            label="Data Structures in Python",
            url="https://www.geeksforgeeks.org/dsa/dsa-tutorial-learn-data-structures-and-algorithms/",
            blurb="a way of organizing and storing data in a computer so that it can be accessed and modified efficiently.",
            check_prompt="Can you explain what data structures are in programming?"
        )
    ],
    "list_indexing": [
        Resource(
            concept="list_indexing",
            label="List Indexing in Python",
            url="https://www.w3schools.com/python/python_lists.asp",
            blurb="a way to access individual elements in a list using their position or index.",
            check_prompt="Can you explain what list indexing is in programming?"
        )
    ],
    "error_handling": [
        Resource(
            concept="error_handling",
            label="Error Handling in Python",
            url="https://www.w3schools.com/python/python_try_except.asp",
            blurb="a way to handle errors in a program gracefully, allowing the program to continue running instead of crashing.",
            check_prompt="Can you explain what error handling is in programming?"
        )
    ],
    "object_oriented_programming": [
        Resource(
            concept="object_oriented_programming",
            label="Object-Oriented Programming in Python",
            url="https://www.w3schools.com/python/python_classes.asp",
            blurb="a programming paradigm that uses objects and classes to organize code and data.",
            check_prompt="Can you explain what object-oriented programming is?"
        )
    ],
    "file_handling": [
        Resource(
            concept="file_handling",
            label="File Handling in Python",
            url="https://www.w3schools.com/python/python_file_handling.asp",
            blurb="a way to read from and write to files in a program.",
            check_prompt="Can you explain what file handling is in programming?"
        )
    ],
    "recursion_base_case": [
        Resource(
            concept="recursion_base_case",
            label="Recursion Base Case in Python",
            url="https://www.geeksforgeeks.org/recursion-in-python/",
            blurb="the condition that stops the recursion from continuing indefinitely.",
            check_prompt="Can you explain what a base case is in recursion?"
        )
    ],
    "types": [
        Resource(
            concept="types",
            label="Data Types in Python",
            url="https://www.w3schools.com/python/python_datatypes.asp",
            blurb="the classification of data that tells the interpreter how the programmer intends to use the data.",
            check_prompt="Can you explain what data types are in programming?"
        )
    ],
    "none_value": [
        Resource(
            concept="none_value",
            label="None Value in Python",
            url="https://www.w3schools.com/python/ref_keyword_none.asp",
            blurb="a special constant in Python that represents the absence of a value or a null value.",
            check_prompt="Can you explain what the None value is in programming?"
        )
    ],
    "dictionaries": [
        Resource(
            concept="dictionaries",
            label="Dictionaries in Python",
            url="https://www.w3schools.com/python/python_dictionaries.asp",
            blurb="a collection of key-value pairs that allows for fast retrieval of values based on their associated keys.",
            check_prompt="Can you explain what dictionaries are in programming?"
        )
    ],
    "scope": [
        Resource(
            concept="scope",
            label="Scope in Python",
            url="https://www.w3schools.com/python/python_scope.asp",
            blurb="the region of a program where a variable is defined and can be accessed.",
            check_prompt="Can you explain what scope is in programming?"
        )
    ],
    "indentation": [
        Resource(
            concept="indentation",
            label="Indentation in Python",
            url="https://www.w3schools.com/python/gloss_python_indentation.asp",
            blurb="the use of whitespace at the beginning of a line to define the structure and flow of a program.",
            check_prompt="Can you explain what indentation is in programming?"
        )
    ],
}

# Error types map to a likely concept. Intentionally cautionary - a wrong
# resource is worse than none, since it sends the student off-track.
ERROR_TYPE_CONCEPTS: dict[str, str] = {
    "RecursionError": "recursion",
    "IndexError": "list_indexing",
    "KeyError": "dictionaries",
    "TypeError": "types",
    "NameError": "scope",
    "UnboundLocalError": "scope",
    "AttributeError": "none_value",
    "IndentationError": "indentation",
    "TabError": "indentation",
}

# Regex patterns that override/refine the error-type guess.
_SNIPPET_PATTERNS: list[tuple[str, str]] = [
    (r"\bdef\s+(\w+)\b[\s\S]*\b\1\s*\(", "recursion"),  # function calls its own name
    (r"\breturn\b", "functions"),
    (r"\bfor\b|\bwhile\b", "loops"),
]

def detect_concept(error_type: str, code_snippet: str = "") -> str | None:
    """Best-effort concept match. Returns None when nothing fits well —
    the student is then guided normally, with no resource injected."""
    concept = ERROR_TYPE_CONCEPTS.get(error_type)
 
    # A self-calling function is a strong recursion signal regardless of
    # what error type was raised, so let it override.
    for pattern, candidate in _SNIPPET_PATTERNS:
        if candidate == "recursion" and re.search(pattern, code_snippet or ""):
            concept = "recursion"
            break
 
    if concept is not None and concept not in CONCEPT_RESOURCES:
        return None
    return concept
 
 
def get_resource(concept: str | None) -> Resource | None:
    if not concept:
        return None
    resources = CONCEPT_RESOURCES.get(concept)

    if not resources:
        return None
    
    return resources[0]
 
 
def check_links(timeout: float = 5.0) -> list[tuple[str, int | str]]:
    """Utility for CI/maintenance: HEAD every curated URL and report any
    that aren't 200. Run this on a schedule so dead links get caught by you
    rather than by a stuck student."""
    import urllib.request
    import urllib.error
 
    results = []
    for resources in CONCEPT_RESOURCES.values():
        for res in resources:
            req = urllib.request.Request(res.url, method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    if r.status != 200:
                        results.append((res.url, r.status))
            except Exception as e:  # noqa: BLE001 - reporting utility
                results.append((res.url, str(e)))
    return results
