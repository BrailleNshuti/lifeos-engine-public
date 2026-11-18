"""`lifeos completion powershell|bash`: a tab-completion script generated from the real argument parser.

Because it is built from the parser, it can never list a command that does not exist or miss a new one. Prints to
the screen; installing it (PowerShell: add the output to your $PROFILE) is your choice.
"""
import argparse


def walk(parser, path=""):
    """{"alpha beta": {"words": [...]}} for every command path; "" is the top level."""
    out = {}
    words, subs = [], None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subs = action
            words += list(action.choices)
        else:
            words += [o for o in action.option_strings if o.startswith("--") or o == "-h"]
    out[path] = {"words": sorted(set(words))}
    if subs:
        for name, child in subs.choices.items():
            out.update(walk(child, f"{path} {name}".strip()))
    return out


def _powershell(tree):
    lines = ["Register-ArgumentCompleter -Native -CommandName lifeos -ScriptBlock {",
             "    param($wordToComplete, $commandAst, $cursorPosition)",
             "    $done = @($commandAst.CommandElements | Select-Object -Skip 1 | ForEach-Object { $_.ToString() } | Where-Object { $_ -notlike '-*' })",
             "    if ($done.Count -gt 0 -and $done[-1] -eq $wordToComplete) { $done = $done[0..($done.Count - 2)] }",
             "    $path = ($done -join ' ')",
             "    $table = @{"]
    for path, node in sorted(tree.items()):
        lines.append(f"        '{path}' = '{' '.join(node['words'])}'")
    lines += ["    }", "    $words = $table[$path]",
              "    if (-not $words -and $done.Count -gt 1) { $words = $table[$done[0]] }",
              "    if (-not $words) { $words = $table[''] }",
              "    $words -split ' ' | Where-Object { $_ -like \"$wordToComplete*\" } |",
              "        ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }",
              "}"]
    return "\n".join(lines)


def _bash(tree):
    lines = ["_lifeos() {", "    local cur=\"${COMP_WORDS[COMP_CWORD]}\" path=\"\" i w",
             "    for ((i=1; i<COMP_CWORD; i++)); do w=\"${COMP_WORDS[i]}\"; [[ $w == -* ]] || path=\"$path $w\"; done",
             "    path=\"${path# }\"", "    local words", "    case \"$path\" in"]
    for path, node in sorted(tree.items()):
        lines.append(f"        '{path}') words='{' '.join(node['words'])}' ;;")
    lines += ["        *) words='" + " ".join(tree[""]["words"]) + "' ;;", "    esac",
              "    COMPREPLY=( $(compgen -W \"$words\" -- \"$cur\") )", "}", "complete -F _lifeos lifeos"]
    return "\n".join(lines)


def script(shell, parser):
    tree = walk(parser)
    if shell == "powershell":
        return _powershell(tree)
    if shell == "bash":
        return _bash(tree)
    raise ValueError(f"Unknown shell '{shell}': use powershell or bash.")
