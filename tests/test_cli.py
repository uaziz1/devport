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


def test_list_all(registry, capsys):
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "[alpha]" in out and "[beta]" in out and "3010" in out


def test_list_one_project(registry, capsys):
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


def test_init_writes_envrc_with_explicit_name(clean_registry, tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    cli.main(["init", "alpha"])
    envrc = project_dir / ".envrc"
    assert envrc.exists()
    assert 'eval "$(devport env alpha)"' in envrc.read_text()


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
