"""
Compatibility patch rules — regex substitutions that fix UE API-break compile
errors in the embedded ConvAI plugin source so a project authored against an
older engine builds cleanly against the target engine.

Selector: target engine version (e.g. "5.8"). The "*" bucket is always applied
(engine-agnostic). Rules are best-effort and idempotent: a rule is a no-op when
its pattern is absent, and every replacement is written so it does NOT re-match
its own pattern (safe on re-runs and on partially-fixed source).

Scope: the embedded ConvAI plugin only (Plugins/ConvAI/...). Helper plugins
(ConvaiHTTP, ConvaiPakManager) are fixed upstream — do NOT add rules for them.

Rule schema:
    name        : short identifier, shown in logs
    file_glob   : project-root-relative path, fnmatch semantics, matched
                  case-insensitively. '*' spans path separators, so
                  'Plugins/ConvAI/*.cpp' matches any .cpp anywhere under the plugin.
    pattern     : raw regex string (Python re syntax)
    replacement : re.sub replacement string (backreferences allowed)
    flags       : optional int of re flags (e.g. re.DOTALL) — defaults to 0
"""

# Any .cpp anywhere under the embedded ConvAI plugin. The glob deliberately
# excludes the ConvaiHTTP / ConvaiPakManager helper folders: 'convai' must be a
# whole path segment, so 'convaihttp' does not match.
CONVAI_PLUGIN_CPP = "Plugins/ConvAI/*.cpp"

# Any source file anywhere under the embedded ConvAI plugin. Same whole-segment
# 'convai' guard as CONVAI_PLUGIN_CPP. Use this for rules that must also reach
# headers — e.g. a delegate member declared in a .h.
CONVAI_PLUGIN_SRC = "Plugins/ConvAI/*"

PATCH_RULES = {
    # Always-on, engine-agnostic. Mirrors patch_target_files(); kept here so the
    # patcher is self-contained. Idempotent, so running both is harmless.
    "*": [
        {
            "name": "target-build-settings-latest",
            "file_glob": "Source/*.Target.cs",
            "pattern": r"DefaultBuildSettings\s*=\s*BuildSettingsVersion\.\w+",
            "replacement": "DefaultBuildSettings = BuildSettingsVersion.Latest",
        },
        {
            "name": "target-include-order-latest",
            "file_glob": "Source/*.Target.cs",
            "pattern": r"IncludeOrderVersion\s*=\s*EngineIncludeOrderVersion\.\w+",
            "replacement": "IncludeOrderVersion = EngineIncludeOrderVersion.Latest",
        },
    ],

    # UE 5.8 API breaks in the embedded ConvAI plugin.
    "5.8": [
        # FJsonObject field accessors now take FStringView; bare narrow string
        # literals no longer implicitly convert. Wrap the literal in TEXT().
        #   GetStringField("foo")        -> GetStringField(TEXT("foo"))
        #   TryGetNumberField("k", Out)  -> TryGetNumberField(TEXT("k"), Out)
        # Idempotent: after wrapping, the char following '(' is 'T', not '"'.
        {
            "name": "json-field-stringview",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r'((?:Get|TryGet)(?:String|Number|Integer|Bool|Array|Object)Field\(\s*)("(?:[^"\\]|\\.)*")',
            "replacement": r"\1TEXT(\2)",
        },
        # TArray::SetNumUninitialized(N, bool) dropped its bool second arg in favor
        # of the EAllowShrinking enum.
        #   SetNumUninitialized(N, true)  -> SetNumUninitialized(N, EAllowShrinking::Yes)
        #   SetNumUninitialized(N, false) -> SetNumUninitialized(N, EAllowShrinking::No)
        # Idempotent: the replacement leaves no bare true/false to re-match.
        {
            "name": "setnumuninitialized-allowshrinking-true",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r"(SetNumUninitialized\s*\(.*?,\s*)true(\s*\))",
            "replacement": r"\1EAllowShrinking::Yes\2",
        },
        {
            "name": "setnumuninitialized-allowshrinking-false",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r"(SetNumUninitialized\s*\(.*?,\s*)false(\s*\))",
            "replacement": r"\1EAllowShrinking::No\2",
        },
        # FString::RemoveAt / TArray::RemoveAt dropped the trailing bool
        # bAllowShrinking in favor of the EAllowShrinking enum (same break).
        #   URL.RemoveAt(URL.Len() - 1, 1, false) -> ..., EAllowShrinking::No)
        # The 3-arg form is the only RemoveAt overload taking a bool tail.
        # Idempotent: the replacement leaves no bare true/false.
        {
            "name": "removeat-allowshrinking-true",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r"(\bRemoveAt\s*\(.*?,\s*)true(\s*\))",
            "replacement": r"\1EAllowShrinking::Yes\2",
        },
        {
            "name": "removeat-allowshrinking-false",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r"(\bRemoveAt\s*\(.*?,\s*)false(\s*\))",
            "replacement": r"\1EAllowShrinking::No\2",
        },
        # TScriptDelegate is now templated on a delegate thread-safety mode, not on
        # FWeakObjectPtr. The old member decl 'TScriptDelegate<FWeakObjectPtr>' both
        # fails to instantiate (TDelegateAccessHandlerBase<FWeakObjectPtr> undefined
        # -> a large ScriptDelegates.h error cascade) and no longer matches the arg
        # type of TMulticastScriptDelegate::Add. Repoint to the default mode.
        #   TScriptDelegate<FWeakObjectPtr> -> TScriptDelegate<FNotThreadSafeDelegateMode>
        # Uses the .h-reaching glob: the offending member lives in a public header.
        # \b + case sensitivity keep 'TMulticastScriptDelegate<...>' from matching.
        # Idempotent: the replacement contains no 'FWeakObjectPtr' to re-match.
        {
            "name": "scriptdelegate-threadsafety-mode",
            "file_glob": CONVAI_PLUGIN_SRC,
            "pattern": r"\bTScriptDelegate\s*<\s*FWeakObjectPtr\s*>",
            "replacement": "TScriptDelegate<FNotThreadSafeDelegateMode>",
        },
        # FJsonObject now stores keys in a shared-string storage type whose
        # FStringType only converts to FString via FString's *explicit*
        # constructor, so copy-init ('FString X = Entry.Key;') no longer compiles.
        # Direct-init through FString(...) restores it. Scoped to the one known
        # site (VoiceType) to stay surgical.
        # Idempotent: after wrapping, the RHS is 'FString(...)', not a bare '.Key'.
        {
            "name": "jsonobject-key-fstring-copy-init",
            "file_glob": CONVAI_PLUGIN_CPP,
            "pattern": r"(FString\s+VoiceType\s*=\s*)(VoiceTypeEntry\.Key)(\s*;)",
            "replacement": r"\1FString(\2)\3",
        },
    ],
}


def get_rules_for_engine(target_engine_version):
    """
    Return the always-on ("*") rules followed by the rules for the given target
    engine version. Unknown versions yield only the always-on rules.

    Args:
        target_engine_version: e.g. "5.8". Falsy -> only always-on rules.

    Returns:
        List of rule dicts.
    """
    rules = list(PATCH_RULES.get("*", []))
    if target_engine_version:
        rules.extend(PATCH_RULES.get(str(target_engine_version), []))
    return rules
