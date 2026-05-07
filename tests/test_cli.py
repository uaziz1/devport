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
