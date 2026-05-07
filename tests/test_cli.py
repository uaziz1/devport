import pytest

from devport import cli


def test_get_resolves_port(registry, capsys):
    cli.main(["alpha", "web"])
    assert capsys.readouterr().out.strip() == "3010"


def test_get_unknown_project_exits(registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["nope", "web"])
    assert "no project 'nope'" in str(exc.value)


def test_get_unknown_port_name_exits(registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["alpha", "nope"])
    assert "no port 'nope'" in str(exc.value)


def test_list_all(registry, capsys, tmp_path, monkeypatch):
    # Run from a clean dir so inference doesn't engage.
    monkeypatch.chdir(tmp_path)
    cli.main(["list", "all"])
    out = capsys.readouterr().out
    assert "[alpha]" in out and "[beta]" in out and "3010" in out


def test_list_no_args_falls_back_to_all_when_no_envrc(registry, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "[alpha]" in out and "[beta]" in out


def test_list_no_args_uses_inference(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    (project_dir / ".envrc").write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(project_dir)
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "[alpha]" in out
    assert "[beta]" not in out  # only the inferred project shown


def test_list_shows_env_var_names(registry, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["list", "beta"])
    out = capsys.readouterr().out
    assert "$WEB_PORT" in out
    assert "$WS_PORT" in out


def test_list_one_project(registry, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["list", "beta"])
    out = capsys.readouterr().out
    assert "[beta]" in out and "[alpha]" not in out


def test_env_emits_exports(registry, capsys):
    cli.main(["env", "beta"])
    out = capsys.readouterr().out
    assert "export WEB_PORT=3020" in out
    assert "export API_PORT=3021" in out
    assert "export WS_PORT=3022" in out


def test_check_known_port(clean_registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "listening_ports", lambda: {})
    cli.main(["check", "3010"])
    out = capsys.readouterr().out
    assert "alpha.web" in out
    assert "(not bound)" in out


def test_check_unknown_port(clean_registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "listening_ports", lambda: {})
    cli.main(["check", "9999"])
    out = capsys.readouterr().out
    assert "(unallocated)" in out


def test_free_skips_used_blocks(clean_registry, capsys):
    # alpha uses 3010-3011, beta uses 3020 → first free block is 3000-3009
    # (3000s above any used block; we expect 3000-3009 since nothing in that range)
    cli.main(["free"])
    out = capsys.readouterr().out.strip()
    assert out == "3000-3009"


def test_doctor_detects_collision(registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "listening_ports", lambda: {})
    with pytest.raises(SystemExit) as exc:
        cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "registry collisions" in out
    assert "alpha.web" in out and "duplicate.web" in out
    assert exc.value.code == 1


def test_doctor_clean_registry(clean_registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "listening_ports", lambda: {})
    with pytest.raises(SystemExit) as exc:
        cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "no registry collisions" in out
    assert exc.value.code == 0


def test_doctor_flags_squatters(clean_registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "listening_ports", lambda: {3050: "node(123)"})
    with pytest.raises(SystemExit):
        cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "unregistered listeners" in out
    assert "3050" in out and "node(123)" in out


def test_help_no_args(capsys):
    cli.main([])
    assert "usage: devport" in capsys.readouterr().out


def test_version(capsys):
    cli.main(["--version"])
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_add_explicit_port(clean_registry, capsys):
    cli.main(["add", "alpha", "ws", "3012"])
    assert capsys.readouterr().out.strip() == "3012"
    assert "ws = 3012" in clean_registry.read_text()


def test_add_auto_allocates_in_existing_block(clean_registry, capsys):
    # alpha has 3010 and 3011; next free in its 3010-3019 block is 3012
    cli.main(["add", "alpha", "ws"])
    assert capsys.readouterr().out.strip() == "3012"


def test_add_auto_allocates_new_block_for_new_project(clean_registry, capsys):
    # alpha (3010-3011) and beta (3020) used; first free 10-block is 3000-3009
    cli.main(["add", "newproj", "web"])
    assert capsys.readouterr().out.strip() == "3000"
    assert "[newproj]" in clean_registry.read_text()


def test_add_rejects_collision(clean_registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["add", "alpha", "newname", "3020"])
    assert "already in use by beta.web" in str(exc.value)


def test_add_rejects_duplicate_name(clean_registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["add", "alpha", "web"])
    assert "alpha.web already exists" in str(exc.value)


def test_add_creates_registry_if_missing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "subdir" / "ports.toml"
    monkeypatch.setenv("DEVPORTS_FILE", str(target))
    cli.main(["add", "fresh", "web", "3010"])
    assert capsys.readouterr().out.strip() == "3010"
    text = target.read_text()
    assert "[fresh]" in text and "web = 3010" in text


def test_add_preserves_comments(tmp_path, monkeypatch, capsys):
    p = tmp_path / "ports.toml"
    p.write_text("# my custom comment\n\n[alpha]\nweb = 3010  # primary\n")
    monkeypatch.setenv("DEVPORTS_FILE", str(p))
    cli.main(["add", "alpha", "api"])
    text = p.read_text()
    assert "# my custom comment" in text
    assert "# primary" in text
    assert "api = 3011" in text


def test_rm_port(clean_registry, capsys):
    cli.main(["rm", "alpha", "api"])
    assert "removed: alpha.api" in capsys.readouterr().out
    text = clean_registry.read_text()
    assert "api = 3011" not in text
    assert "web = 3010" in text  # other ports preserved


def test_rm_whole_project(clean_registry, capsys):
    cli.main(["rm", "beta"])
    assert "removed project: beta" in capsys.readouterr().out
    text = clean_registry.read_text()
    assert "[beta]" not in text
    assert "[alpha]" in text  # other projects preserved


def test_rm_unknown_project(clean_registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["rm", "nope"])
    assert "no project 'nope'" in str(exc.value)


def test_rename_port(clean_registry, capsys):
    cli.main(["rename", "alpha", "web", "frontend"])
    assert "alpha.web -> alpha.frontend" in capsys.readouterr().out
    text = clean_registry.read_text()
    assert "frontend = 3010" in text
    assert "web = 3010" not in text


def test_rename_preserves_inline_comment(tmp_path, monkeypatch, capsys):
    p = tmp_path / "ports.toml"
    p.write_text("[alpha]\nweb = 3010  # primary frontend\n")
    monkeypatch.setenv("DEVPORTS_FILE", str(p))
    cli.main(["rename", "alpha", "web", "frontend"])
    assert "# primary frontend" in p.read_text()


def test_rename_rejects_existing_name(clean_registry):
    with pytest.raises(SystemExit) as exc:
        cli.main(["rename", "alpha", "web", "api"])
    assert "already exists" in str(exc.value)


def test_add_with_inferred_project(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    (project_dir / ".envrc").write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["add", "ws"])  # no project arg
    assert capsys.readouterr().out.strip() == "3012"  # next slot in alpha's block


def test_add_with_inferred_project_and_explicit_port(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    (project_dir / ".envrc").write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["add", "ws", "5050"])
    assert capsys.readouterr().out.strip() == "5050"


def test_add_walks_up_for_envrc(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    sub = project_dir / "src" / "components"
    sub.mkdir(parents=True)
    (project_dir / ".envrc").write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(sub)  # deep inside the project
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["add", "ws"])
    assert capsys.readouterr().out.strip() == "3012"


def test_add_errors_when_no_envrc_to_infer_from(clean_registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        cli.main(["add", "ws"])
    assert "no project inferred" in str(exc.value)


def test_bare_get_with_inferred_project(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    (project_dir / ".envrc").write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(project_dir)
    cli.main(["web"])  # no project arg
    assert capsys.readouterr().out.strip() == "3010"


def test_add_touches_envrc_when_direnv_present(clean_registry, tmp_path, monkeypatch):
    import time

    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    envrc = project_dir / ".envrc"
    envrc.write_text('eval "$(devport env alpha)"\n')
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(
        cli.shutil, "which",
        lambda exe: "/usr/bin/direnv" if exe == "direnv" else None,
    )

    before = envrc.stat().st_mtime_ns
    time.sleep(0.01)
    cli.main(["add", "ws"])
    after = envrc.stat().st_mtime_ns
    assert after > before


def test_init_writes_envrc_with_explicit_name(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "alpha"])
    envrc = project_dir / ".envrc"
    assert envrc.exists()
    assert 'eval "$(devport env alpha)"' in envrc.read_text()


def test_init_shows_summary_with_env_var_and_examples(
    clean_registry, tmp_path, capsys, monkeypatch
):
    project_dir = tmp_path / "newapp"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init"])
    out = capsys.readouterr().out
    # Shows the registry block with env var name
    assert "[newapp]" in out
    assert "$WEB_PORT" in out
    # Shows the next-steps hint
    assert "Replace `3000`" in out
    assert "$WEB_PORT" in out
    assert "package.json" in out
    assert "docker-compose.yml" in out


def test_init_uses_cwd_basename_when_no_arg(clean_registry, tmp_path, monkeypatch):
    project_dir = tmp_path / "alpha"  # match an existing project
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init"])
    assert 'eval "$(devport env alpha)"' in (project_dir / ".envrc").read_text()


def test_init_idempotent(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init"])
    cli.main(["init"])  # second run should not duplicate the eval line
    text = (project_dir / ".envrc").read_text()
    assert text.count('eval "$(devport env alpha)"') == 1
    assert "already wired" in capsys.readouterr().out


def test_init_appends_to_existing_envrc(clean_registry, tmp_path, monkeypatch):
    project_dir = tmp_path / "alpha"
    project_dir.mkdir()
    (project_dir / ".envrc").write_text("export FOO=bar\n")
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init"])
    text = (project_dir / ".envrc").read_text()
    assert "export FOO=bar" in text
    assert 'eval "$(devport env alpha)"' in text


def test_init_auto_adds_web_port_for_new_project(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "newproj"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init"])
    out = capsys.readouterr().out
    assert "added newproj.web" in out
    # registry now has newproj with a web port
    text = clean_registry.read_text()
    assert "[newproj]" in text and "web =" in text
    # .envrc written
    assert (project_dir / ".envrc").exists()


def test_init_existing_project_does_not_add_port(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "alpha"  # already has web=3010, api=3011
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    before = clean_registry.read_text()
    cli.main(["init"])
    out = capsys.readouterr().out
    assert "already in registry" in out
    assert "web=3010" in out
    # registry contents unchanged
    assert clean_registry.read_text() == before


def test_init_rejects_invalid_name(clean_registry, tmp_path, monkeypatch):
    project_dir = tmp_path / "weird name"  # space — invalid
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    with pytest.raises(SystemExit) as exc:
        cli.main(["init"])
    assert "not a valid project name" in str(exc.value)


def test_init_adopt_flow_with_yes_rewrites_files(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3000"}}\n'
    )
    (project_dir / "docker-compose.yml").write_text(
        'services:\n  web:\n    environment:\n      - URL=http://localhost:3000/api\n'
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "--yes"])
    out = capsys.readouterr().out
    # Plan was printed
    assert "Detected" in out
    assert "myapp.web = 3000" in out
    # Files rewritten
    assert "rewrote 2 occurrence(s)" in out
    pkg = (project_dir / "package.json").read_text()
    compose = (project_dir / "docker-compose.yml").read_text()
    assert "--port ${WEB_PORT}" in pkg
    assert "localhost:${WEB_PORT}" in compose


def test_init_adopt_dry_run_makes_no_changes(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3000"}}\n'
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "--dry-run"])
    out = capsys.readouterr().out
    assert "dry-run" in out
    # File untouched
    assert "--port 3000" in (project_dir / "package.json").read_text()
    # Registry untouched
    assert "[myapp]" not in clean_registry.read_text()


def test_init_adopt_reallocates_on_collision(clean_registry, tmp_path, capsys, monkeypatch):
    # alpha.web is on 3010 in the fixture. Make myapp use 3010 → should re-allocate.
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3010"}}\n'
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "--yes"])
    out = capsys.readouterr().out
    assert "collides with alpha.web" in out
    assert "re-allocated" in out
    # Registry has myapp with a port that ISN'T 3010 (since 3010 was alpha.web)
    text = clean_registry.read_text()
    assert "[myapp]" in text
    # Parse out myapp's web port specifically
    in_myapp = False
    myapp_ports: list[int] = []
    for line in text.splitlines():
        s = line.strip()
        if s == "[myapp]":
            in_myapp = True
            continue
        if s.startswith("[") and s.endswith("]"):
            in_myapp = False
            continue
        if in_myapp and "=" in s:
            myapp_ports.append(int(s.split("=")[1].strip()))
    assert myapp_ports
    assert 3010 not in myapp_ports  # didn't claim alpha's port
    # File now uses ${WEB_PORT}
    pkg = (project_dir / "package.json").read_text()
    assert "--port ${WEB_PORT}" in pkg


def test_init_no_adopt_flag_skips_scan(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3000"}}\n'
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "--no-adopt"])
    out = capsys.readouterr().out
    # Bare init: no detection, no rewrite, just adds web port
    assert "Detected" not in out
    assert "added myapp.web" in out
    # File untouched
    assert "--port 3000" in (project_dir / "package.json").read_text()


def test_init_adopt_prompt_no_aborts(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3000"}}\n'
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    with pytest.raises(SystemExit) as exc:
        cli.main(["init"])
    assert exc.value.code == 1
    # File untouched
    assert "--port 3000" in (project_dir / "package.json").read_text()


def test_adopt_finds_hardcoded_ports(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DEVPORTS_FILE", str(tmp_path / "noop.toml"))
    project = tmp_path / "myapp"
    project.mkdir()
    (project / "package.json").write_text(
        '{"scripts": {"dev": "vite --port 3000"}}'
    )
    (project / "docker-compose.yml").write_text(
        "services:\n  web:\n    ports:\n      - localhost:4000:3000\n"
    )
    cli.main(["adopt", str(project)])
    out = capsys.readouterr().out
    assert "3000" in out
    assert "4000" in out
    assert "package.json" in out
    assert "docker-compose.yml" in out
