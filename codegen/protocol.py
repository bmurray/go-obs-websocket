# TODO: No warning is given for struct fields whose names match function names.
# Maybe bring the reserved list back.

import json
import os
import sys
from typing import Dict, List, Tuple

package = "obsws"

doc = "https://github.com/Palakis/obs-websocket/blob/master/docs/generated/protocol.md"

disclaimer = """
// This file is automatically generated.
// https://github.com/christopher-dG/go-obs-websocket/blob/master/codegen/protocol.py
"""

# TODO: Test the less clear ones.
type_map = {
    "bool": "bool",
    "boolean": "bool",
    "int": "int",
    "float": "float64",
    "double": "float64",
    "string": "string",
    "array": "[]interface{}",
    "object": "map[string]interface{}",
    "array of objects": "[]map[string]interface{}",
    "object|array": "interface{}",
    "scene|array": "[]map[string]interface{}",
    "source|array": "[]map[string]interface{}",
}

unknown_types = []


def process_json(d: Dict):
    """Generate Go code for the entire protocol file."""
    ("--events" in sys.argv or "--all" in sys.argv) and gen_events(d["events"])
    ("--requests" in sys.argv or "--all" in sys.argv) and gen_requests(d["requests"])
    ("--typeswitches" in sys.argv or "--all" in sys.argv) and gen_typeswitches(d)


def gen_category(prefix: str, category: str, data: Dict):
    """Generate all events or requests in one category."""
    func = gen_event if prefix == "events" else gen_request
    content = "\n".join(
        filter(
            lambda s: not s.isspace(),
            "\n".join(func(thing) for thing in data).split("\n"),
        )
    )

    with open(f"{prefix}_{category}.go".replace(" ", "_"), "w") as f:
        f.write(
            f"""
        package {package}

        {disclaimer}

        {content}
        """
        )


def gen_events(events: Dict):
    """Generate all events."""
    for category, data in events.items():
        gen_category("events", category, data)


def gen_event(data: Dict) -> str:
    """Write Go code with a type definition and interface functions."""
    struct = f"""
    type {data["name"]}Event struct {{
        {go_struct_variables(go_variables(data.get("returns", [])))}
        _event `json:",squash"`
    }}
    """
    # else:
    #     struct = f"type {data['name']}Event _event"

    description = newlinify(f"{data['name']}Event : {data['description']}")
    if not description.endswith("."):
        description += "."
    if data.get("since"):
        description += (
            f"\n// Since obs-websocket version: {data['since'].capitalize()}."
        )

    return f"""
    {description}
    // {doc}#{data["heading"]["text"].lower()}
    {struct}
    """


def gen_requests(requests: Dict):
    """Generate all requests and responses."""
    for category, data in requests.items():
        gen_category("requests", category, data)


def gen_request(data: Dict) -> str:
    """Write Go code with type definitions and interface functions."""
    if data.get("params"):
        struct = f"""
        type {data["name"]}Request struct {{
            {go_struct_variables(go_variables(data["params"]))}
            _request `json:",squash"`
        }}
        """
    else:
        struct = f"type {data['name']}Request struct {{ _request }}"

    description = newlinify(f"{data['name']}Request : {data['description']}")
    if description and not description.endswith("."):
        description += "."
    if data.get("since"):
        description += (
            f"\n// Since obs-websocket version: {data['since'].capitalize()}."
        )

    request = f"""
    {description}
    // {doc}#{data["heading"]["text"].lower()}
    {struct}

    {gen_request_new(data)}

    // Send sends the request and returns a channel to which the response will be sent.
    func (r {data["name"]}Request) Send(c Client) (chan {data["name"]}Response, error) {{
        generic, err := c.SendRequest(r)
        if err != nil {{
            return nil, err
	    }}
	    future := make(chan {data["name"]}Response)
	    go func() {{ future <- (<-generic).({data["name"]}Response) }}()
	    return future, nil
    }}
    """

    if data.get("returns"):
        struct = f"""
        type {data["name"]}Response struct {{
            {go_struct_variables(go_variables(data["returns"]))}
            _response `json:",squash"`
        }}
        """
    else:
        struct = (
            f"""type {data["name"]}Response struct {{ _response `json:",squash"`}}"""
        )

    description = f"// {data['name']}Response : Response for {data['name']}Request."
    if data.get("since"):
        description += (
            f"\n// Since obs-websocket version: {data['since'].capitalize()}."
        )

    response = f"""
    {description}
    // {doc}#{data["heading"]["text"].lower()}
    {struct}
    """

    return f"{request}\n\n{response}"


def gen_request_new(request: Dict):
    """Generate Go code with a New___Request function for a request type."""
    base = f"""
    // New{request["name"]}Request returns a new {request["name"]}Request.
    func New{request["name"]}Request(\
    """
    variables = go_variables(request.get("params", []), export=False)
    if not variables:
        sig = f"{base}) {request['name']}Request"
        constructor_args = f"""\
        {{_request{{
            ID_: getMessageID(),
            Type_: "{request["name"]}",
        }}}}
        """
    else:
        args = "\n".join(
            f"{'_type' if var['name'] == 'type' else var['name']} {var['type']},"
            for var in variables
        )
        constructor_args = (
            "{\n"
            + "\n".join(
                "_type," if var["name"] == "type" else f"{var['name']},"
                for var in variables
            )
            + f"""
        _request{{
            ID_: getMessageID(),
            Type_: "{request["name"]}",
        }},
        }}
        """
        )
        if len(variables) == 1:
            sig = f"{base}{args}) {request['name']}Request"
        else:
            sig = f"""
            {base}
                {args}
            ) {request["name"]}Request\
            """
    return f"{sig} {{ return {request['name']}Request{constructor_args} }}"


def gen_typeswitches(data: Dict):
    """Generate a Go file with a mappings from type names to structs."""
    req_map = {}
    for category in data["requests"].values():
        for r in category:
            req_map[r["name"]] = f"&{r['name']}Request{{}}"
    req_entries = "\n".join(f'"{k}": {v},' for k, v in req_map.items())

    resp_map = {}
    for category in data["requests"].values():
        for r in category:
            resp_map[r["name"]] = f"&{r['name']}Response{{}}"
    resp_entries = "\n".join(f'"{k}": {v},' for k, v in resp_map.items())

    event_map = {}
    for category in data["events"].values():
        for e in category:
            event_map[e["name"]] = f"&{e['name']}Event{{}}"
    event_entries = "\n".join(f'"{k}": {v},' for k, v in event_map.items())

    resp_switch_list = []
    for resp in resp_map:
        resp_switch_list.append(
            f"""\
        case *{resp}Response:
            return *r\
        """
        )
    resp_switch_entries = "\n".join(resp_switch_list)

    event_switch_list = []
    for event in event_map:
        event_switch_list.append(
            f"""\
        case *{event}Event:
            return *e\
        """
        )
    event_switch_entries = "\n".join(event_switch_list)

    with open("typeswitches.go", "w") as f:
        f.write(
            f"""
        package {package}

        {disclaimer}

        var ReqMap = map[string]Request{{
            {req_entries}
        }}

        var respMap = map[string]Response{{
            {resp_entries}
        }}

        var eventMap = map[string]Event{{
            {event_entries}
        }}

        func derefResponse(r Response) Response {{
            switch r := r.(type) {{
            {resp_switch_entries}
            default:
                return nil
            }}
        }}

        func derefEvent(e Event) Event {{
            switch e := e.(type) {{
            {event_switch_entries}
            default:
                return nil
            }}
        }}
        """
        )


def go_variables(variables: List[Dict], export: bool = True) -> str:
    """
    Convert a list of variable names into Go code to be put
    inside a struct definition.
    """
    vardicts, varnames = [], []
    for v in variables:
        typename, optional = optional_type(v["type"])
        varname = go_var(v["name"], export=export)
        vardicts.append(
            {
                "name": varname,
                "type": type_map[typename.lower()],
                "tag": f'`json:"{v["name"]}"`',
                "description": v["description"].replace("\n", " "),
                "optional": optional,
                "unknown": typename.lower() in unknown_types,
                "actual_type": v["type"],
                "duplicate": varname in varnames,
            }
        )
        varnames.append(varname)
    return vardicts


def go_var(s: str, export: bool = True) -> str:
    """Convert a variable name in the input file to a Go variable name."""
    s = f"{(str.upper if export else str.lower)(s[0])}{s[1:]}"
    for sep in ["-", "_", ".*.", "[].", "."]:
        while sep in s:
            _len = len(sep)
            if s.endswith(sep):
                s = s[:-_len]
                continue
            i = s.find(sep)
            s = f"{s[:i]}{s[i+_len].upper()}{s[i+_len+1:]}"

    return s.replace("Id", "ID").replace("Obs", "OBS").replace("Fps", "FPS")


def go_struct_variables(variables: List[Dict]) -> str:
    """Generate Go code containing struct field definitions."""
    lines = []
    for var in variables:
        if var["description"]:
            description = (
                var["description"]
                .replace("e.g. ", "e.g.")
                .replace(". ", "\n")
                .replace("e.g.", "e.g. ")
            )
            for desc_line in description.split("\n"):
                desc_line = desc_line.strip()
                if desc_line and not desc_line.endswith("."):
                    desc_line += "."
                lines.append(f"// {desc_line}")
        lines.append(f"// Required: {'Yes' if not var['optional'] else 'No'}.")
        todos = []
        if var["unknown"]:
            todos.append(f"Unknown type ({var['actual_type']})")
        if var["duplicate"]:
            todos.append("Duplicate name")
        todos = " ".join(f"TODO: {todo}." for todo in todos)
        if todos:
            lines.append(f"// {todos}")
        lines.append(f"{var['name']} {var['type']} {var['tag']}")
    return "\n".join(lines)


def newlinify(s: str, comment: bool = True) -> str:
    """Put each sentence of a string onto its own line."""
    s = s.replace("e.g. ", "e.g.").replace(". ", "\n").replace("e.g.", "e.g. ")
    if comment:
        s = "\n".join(
            [f"// {_s}" if not _s.startswith("//") else _s for _s in s.split("\n")]
        )
    return s


def optional_type(s: str) -> Tuple[str, bool]:
    """Determine if a type is optional and parse the actual type name."""
    if s.endswith("(optional)"):
        return s[: s.find("(optional)")].strip(), True
    return s, False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Missing filename argument")
        exit(1)

    if not os.path.isfile(sys.argv[1]):
        print(f"file '{sys.argv[1]}' does not exist")
        exit(1)

    with open(sys.argv[1]) as f:
        d = json.load(f)

    process_json(d)
    os.system("gofmt -w *.go")
