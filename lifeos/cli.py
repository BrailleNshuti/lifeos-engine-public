"""lifeos: command line for the LifeOS Engine."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from . import backup, bakeoff, calibrate, arch, canary, decision, demo, digest, earn, experiment, prove, savings, selftest, cockpit, exam, governor, history, hooks, learn, lint, mistakes, numbers, panel, pipeline, redact, release, today, vocab, kaizen, lab, log, mcp, replay, router, runs, seats, schema, showcase, sortcsv, stale, study, verify
from .delegate import run_delegate
from .ask import ADAPTERS, MINIMAL, PROVIDERS, AskError, Blocked, ToolMissing, provider_status, run_ask, run_review
from .context import build_pack, explain_pack, render_explanation
from .guard import scan_paths, scan_staged, staged_files
from .home import CORE_FILES, HomeError, estimate_tokens, find_home
from .labcard import LabRefused
from .store import append_run_record, new_run_id, read_run_records, utc_now_iso
from .tasks import list_tasks, new_task
from .week import build_redteam_pack, draft_weekly_review, render_markdown, week_numbers

CORE_TOKEN_CAP = 2000
LINE_LIMITS = {"rules.md": 60, "me.md": 15, "now.md": 60, "CLAUDE.md": 60, "AGENTS.md": 40}


def cmd_task(args):
    home = find_home(args.home)
    if args.action == "new":
        path = new_task(home, " ".join(args.sentence), route=args.route, level=args.level, due=args.due or "")
        print(path.relative_to(home))
        print("Next: write the done_when line yourself.")
    else:
        for t in list_tasks(home, args.status):
            print(f"{t['id']:<40} {t['status']:<7} {t['due']:<11} {t['goal']}")
    return 0


def cmd_week(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = draft_weekly_review(home, args.week)
        print(target.relative_to(home))
        return 0
    if getattr(args, "redteam", False):
        print(build_redteam_pack(home, args.week), end="")
        return 0
    numbers = week_numbers(home, args.week)
    print(json.dumps(numbers, indent=2) if args.json else render_markdown(numbers))
    return 0


def cmd_log(args):
    home = find_home(args.home)
    if args.log_action == "proof":
        line = log.log_proof(home, args.area, args.proof, args.link, date=args.date)
    elif args.log_action == "ledger":
        line = log.log_ledger(home, args.task, args.model, args.minutes, args.note, date=args.date)
    elif args.log_action == "health":
        line = log.log_health(home, args.sleep, args.gym, args.energy, note=args.note, date=args.date)
    elif args.log_action == "hours":
        line = log.log_hours(home, args.area, args.hours, note=args.note, date=args.date)
    else:
        return 2
    print(line)
    return 0


def cmd_runs(args):
    home = find_home(args.home)
    summary = runs.summarize_runs(home, status=args.status, model=args.model, task=args.task, limit=args.limit)
    print(json.dumps(summary, indent=2) if args.json else runs.render_runs(summary))
    return 0


def cmd_verify(args):
    result = verify.verify_chain(find_home(args.home), anchor=args.anchor)
    print(json.dumps(result, indent=2) if args.json else verify.render(result))
    return 0 if result["ok"] and result["anchor_found"] is not False else 1


def cmd_replay(args):
    try:
        out = replay.replay_run(find_home(args.home), args.run_id)
    except replay.ReplayError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2) if args.json else replay.render(out))
    return 0 if out["identical"] else (2 if not out["supported"] else 1)


def cmd_canary(args):
    g, o = canary.guard_score(), canary.outbound_check()
    print(json.dumps({"guard": g, "outbound": o}, indent=2) if args.json else canary.render(g, o))
    return 0 if not g["misses"] and not g["benign_flagged"] and o["ok"] else 1


def cmd_panel(args):
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    try:
        out = panel.run_panel(find_home(args.home), models, args.task, args.budget, full=args.full)
    except panel.PanelError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    except (ToolMissing, Blocked, AskError) as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 3
    print(json.dumps({k: out[k] for k in ("pack_sha256", "run_ids", "failed", "report")}, indent=2) if args.json
          else "Panel\n" + out["text"])
    return 0


def cmd_rate(args):
    home = find_home(args.home)
    try:
        from .context import task_file
        from .delegate import task_text
        text = task_text(task_file(home, args.task))
        row = learn.add_rating(home, args.task, args.model, args.score, text, note=args.note)
    except (learn.LearnError, ValueError, FileNotFoundError) as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(f"rated {row['model']} {row['score']}/5 for: {row['kind']}")
    return 0


def cmd_learn(args):
    home = find_home(args.home)
    rep = learn.report(home)
    print(json.dumps(rep, indent=2) if args.json else learn.render(rep))
    return 0


def cmd_predict(args):
    try:
        pid = calibrate.predict(find_home(args.home), args.claim, args.p)
    except calibrate.CalibrationError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(f"{pid} recorded at {args.p} %. Resolve it later: lifeos resolve {pid} yes|no")
    return 0


def cmd_resolve(args):
    try:
        calibrate.resolve(find_home(args.home), args.id, args.outcome == "yes")
    except calibrate.CalibrationError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(f"{args.id} resolved: {args.outcome}")
    return 0


def cmd_calibration(args):
    rep = calibrate.report(find_home(args.home))
    print(json.dumps(rep, indent=2) if args.json else calibrate.render(rep))
    return 0


def cmd_mistakes(args):
    items = mistakes.quiz(find_home(args.home), args.count)
    if args.json:
        print(json.dumps(items, indent=2))
    elif not items:
        print("No open mistakes. Practise with `lifeos study attempt` and they will show up here.")
    else:
        print("Your mistake quiz (answers hidden; check with the study desk):")
        for n, item in enumerate(items, 1):
            print(f"{n}. {item['prompt']}  [{item['id']}]")
    return 0


def cmd_vocab(args):
    home = find_home(args.home)
    try:
        if args.vocab_action == "add":
            vocab.add(home, args.word, args.meaning, args.example)
            print(f"added: {args.word}")
        elif args.vocab_action == "answer":
            vocab.answer(home, args.word, args.result == "good")
            print(f"{args.word}: {args.result}")
        else:
            words = vocab.due(home)[:args.count]
            if not words:
                print("Nothing due. Add words from your own day: lifeos vocab add \"die Wohnung\" \"the flat\"")
            for w in words:
                print(f"{w['word']}" + (f"  = {w['meaning']}" if args.reveal else "") + (f"\n   {w['example']}" if args.reveal and w["example"] else ""))
    except vocab.VocabError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    return 0


def cmd_numbers(args):
    commands = len(next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices)
    data = numbers.build(find_home(args.home), commands=commands)
    page = numbers.render(data)
    if args.html:
        Path(args.html).write_text(numbers.render_html(data), encoding="utf-8")
        print(f"wrote {args.html}")
    elif args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(json.dumps(data, indent=2) if args.json else page)
    return 0


def cmd_savings(args):
    s = savings.compute(find_home(args.home))
    print(json.dumps(s, indent=2) if args.json else savings.render(s))
    return 0


def cmd_demo(args):
    try:
        steps = demo.run(args.example)
    except (OSError, ValueError, KeyError) as err:
        print(f"lifeos: demo needs the examples/demo-home folder from the repository ({err}).", file=sys.stderr)
        return 2
    print(json.dumps(steps, indent=2) if args.json else demo.render(steps))
    return 0 if all(s["ok"] for s in steps) else 1


def cmd_history_scan(args):
    try:
        out = history.scan(".", args.max_commits)
    except (OSError, subprocess.CalledProcessError):
        print("lifeos: run this inside a git repository.", file=sys.stderr)
        return 2
    for f in out["findings"]:
        print(f"BLOCK {f['commit']} {f['file']}  {f['kind']}  {f['excerpt']}")
    if out["findings"]:
        print(f"\n{len(out['findings'])} finding(s) in {out['commits']} commit(s). A removed secret is still in the history: "
              "rotate it, then clean the history.", file=sys.stderr)
        return 1
    print(f"history ok: {out['commits']} commit(s) checked", file=sys.stderr)
    return 0


def cmd_hook(args):
    try:
        path = hooks.install(".", args.force)
    except hooks.HookError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(f"installed {path}: the guard now runs before every commit")
    return 0


def cmd_prove(args):
    commands = len(next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices)
    out = prove.run(find_home(args.home), run_tests=not args.skip_tests, commands=commands)
    page = prove.render(out)
    if args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        print(f"wrote {args.out}: {'PASS' if out['ok'] else 'FAIL'}")
    else:
        print(page)
    return 0 if out["ok"] else 1


def cmd_digest(args):
    d = digest.build(find_home(args.home))
    print(json.dumps(d, indent=2) if args.json else digest.render(d))
    return 0


def cmd_arch(args):
    page = arch.page()
    if args.check:
        path = Path(args.check)
        if path.exists() and path.read_text(encoding="utf-8") == page:
            print(f"{args.check} matches the code")
            return 0
        print(f"{args.check} is missing or stale: run `lifeos arch --write {args.check}`", file=sys.stderr)
        return 1
    if args.write:
        Path(args.write).write_text(page, encoding="utf-8", newline="\n")
        print(f"wrote {args.write}")
    else:
        print(page)
    return 0


def cmd_experiment(args):
    home = find_home(args.home)
    try:
        if args.exp_action == "start":
            e = experiment.start(home, args.change, args.metric, args.days)
            print(f"{e['id']} started: {args.metric} baseline {e['baseline']} ({e['baseline_points']} data points). "
                  f"Finish after {e['days']} days: lifeos experiment end {e['id']}")
        elif args.exp_action == "end":
            out = experiment.end(home, args.id)
            print(f"{out['id']}: {out['verdict'].upper()}. {out['why']}")
        else:
            print(experiment.render(experiment.list_all(home)))
    except experiment.ExperimentError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    return 0


def cmd_pipeline(args):
    home = find_home(args.home)
    try:
        rows = pipeline.run(home, args.name, main, execute=args.run)
    except pipeline.PipelineError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(pipeline.render(rows, args.run))
    return 1 if any(r["status"] == "failed" for r in rows) else 0


def cmd_decide(args):
    home = find_home(args.home)
    try:
        if args.dec_action == "add":
            path = decision.record(home, args.title, args.why, args.revisit, args.predict, args.p)
            print(f"Recorded {path.name}")
        else:
            rows = decision.due(home) if args.dec_action == "due" else decision.list_all(home)
            print(decision.render(rows))
    except decision.DecisionError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    return 0


def cmd_backup(args):
    try:
        if args.check:
            res = backup.check(args.check)
            print(f"backup ok: {res['files']} file(s) match the manifest." if res["ok"]
                  else "backup BAD:\n" + "\n".join(res["errors"]))
            return 0 if res["ok"] else 1
        if not args.out:
            print("lifeos: give --out DIR or --check DIR", file=sys.stderr)
            return 2
        folder = backup.make(find_home(args.home), args.out)
        print(f"Backed up to {folder}. Check it any time: lifeos backup --check {folder}")
    except backup.BackupError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    return 0


def cmd_redact(args):
    code = 0
    for name in args.files:
        try:
            dest, n = redact.copy(name, args.out)
            print(f"{dest}: {n} line(s) redacted")
        except redact.RedactError as err:
            print(f"lifeos: {err}", file=sys.stderr)
            code = 2
    return code


def cmd_release(args):
    try:
        p = release.plan(args.repo)
    except OSError as err:
        print(f"lifeos: cannot read the repository: {err}", file=sys.stderr)
        return 2
    print(release.render(p))
    return 1 if p["problems"] else 0


def cmd_earn(args):
    print(earn.render(earn.review(find_home(args.home), days=args.days)))
    return 0


def cmd_today(args):
    print(today.render(today.build(find_home(args.home))))
    return 0


def cmd_lint(args):
    found = lint.check(find_home(args.home))
    print(lint.render(found))
    return 1 if found else 0


def cmd_stale(args):
    print(stale.render(stale.find(find_home(args.home), days=args.days)))
    return 0


def cmd_schema(args):
    page = schema.page()
    if args.check:
        path = Path(args.check)
        if path.exists() and path.read_text(encoding="utf-8") == page:
            print(f"{args.check} matches the code")
            return 0
        print(f"{args.check} is missing or stale: run `lifeos schema --write {args.check}`", file=sys.stderr)
        return 1
    if args.write:
        Path(args.write).write_text(page, encoding="utf-8", newline="\n")
        print(f"wrote {args.write}")
    else:
        print(page)
    return 0


def cmd_selftest(args):
    rows = selftest.run(main, args.example)
    print(selftest.render(rows))
    return 0 if all(r["ok"] for r in rows) else 1


def cmd_kaizen(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = kaizen.draft_system_health(home, month=args.month)
        print(target.relative_to(home))
        return 0
    report = kaizen.system_health(home, month=args.month)
    print(json.dumps(report, indent=2) if args.json else kaizen.render_system_health(report), end="" if not args.json else "\n")
    return 0


def cmd_route(args):
    home = find_home(args.home)
    decision = router.evaluate_route(home, " ".join(args.target), tier=args.tier, full=args.full)
    print(json.dumps(decision, indent=2) if args.json else router.render_route(decision))
    return 1 if decision["blocked"] else 0


def cmd_cockpit(args):
    home = find_home(args.home)
    if getattr(args, "serve", False):
        print(f"LifeOS Cockpit serving on http://127.0.0.1:{args.port}/#learning", file=sys.stderr)
        cockpit.serve_cockpit(home, port=args.port)
        return 0
    target = cockpit.export_cockpit(home, out_path=args.export)
    try:
        print(target.relative_to(home))
    except ValueError:
        print(target)
    return 0


def cmd_exam(args):
    home = find_home(args.home)
    if getattr(args, "score_skill", None) is not None:
        res = exam.record_exam_score(home, args.score_skill, args.score_pct, proof_link=args.link or "reviews/exam.md")
        print(json.dumps(res))
        return 0
    if getattr(args, "draft", False):
        target = exam.write_exam_draft(home, month=args.month, module=args.module, overwrite=args.overwrite)
        print(target.relative_to(home))
        return 0
    print(exam.generate_monthly_exam(home, month=args.month, module=args.module))
    return 0


def cmd_study(args):
    home = find_home(args.home)
    if args.study_action == "sources":
        rows = study.list_sources(home)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                print(f"{row['subject']:<18} {row['words']:>6} words  {row['path']}  ({row['sha256'][:10]})")
        return 0
    if args.study_action == "import":
        source_path = Path(args.file)
        source = source_path.read_text(encoding="utf-8")
        title = args.title or source_path.stem
        target = study.save_note(home, title, args.subject, source, source_url=args.source_url)
        print(target.relative_to(home).as_posix())
        return 0
    if args.study_action == "bank":
        target = study.write_question_bank(home, args.source, overwrite=args.overwrite)
        print(target.relative_to(home).as_posix())
        return 0
    if args.study_action == "curricula":
        print(json.dumps(study.list_curricula(home), ensure_ascii=False, indent=2))
        return 0
    if args.study_action == "refresh":
        print(json.dumps(study.refresh_question_banks(home, curriculum_id=args.curriculum or ""), ensure_ascii=False))
        return 0
    if args.study_action == "gaps":
        print(json.dumps(study.study_snapshot(home).get("gaps", []), ensure_ascii=False, indent=2))
        return 0
    if args.study_action == "verify":
        result = study.set_question_trust(home, args.bank, args.question, args.trust)
        print(json.dumps(result))
        return 0
    if args.study_action == "attempt":
        result = study.record_attempt(home, args.question, args.rating, elapsed_seconds=args.seconds)
        print(json.dumps(result))
        return 0
    if args.study_action == "exam":
        result = study.compose_exam(
            home, title=args.title, subject=args.subject or "", count=args.count, minutes=args.minutes,
        )
        print(json.dumps({**result, "exam_path": result["exam_path"].relative_to(home).as_posix(),
                          "key_path": result["key_path"].relative_to(home).as_posix()}))
        return 0
    return 2


def cmd_bakeoff(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = bakeoff.write_bakeoff(
            home, quarter=args.quarter, task_type=args.task_type,
            model_a=args.model_a, model_b=args.model_b, scores_json=args.scores, overwrite=args.overwrite,
        )
        print(target.relative_to(home))
        return 0
    scores = json.loads(args.scores) if args.scores else None
    print(bakeoff.render_bakeoff_card(args.quarter or "2026-Q4", args.task_type, model_a=args.model_a, model_b=args.model_b, scores=scores))
    return 0


def cmd_showcase(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = showcase.write_weekly_post(home, week=args.week, overwrite=args.overwrite)
        print(target.relative_to(home))
        return 0
    print(showcase.generate_weekly_post(home, week=args.week))
    return 0


def cmd_context(args):
    home = find_home(args.home)
    if getattr(args, "explain", False):
        print(render_explanation(explain_pack(home, args.task, args.budget)))
        return 0
    pack, tokens = build_pack(home, args.task, args.budget)
    print(pack)
    print(f"[context pack: about {tokens} tokens, budget {args.budget}]", file=sys.stderr)
    return 0


def cmd_ask(args):
    home = find_home(args.home)
    try:
        estimate = build_pack(home, args.task, args.budget, task_first=True, names=None if args.full else MINIMAL)[1]
        gate = governor.check(home, args.model, estimate)
    except (ValueError, FileNotFoundError, OSError):
        gate = None  # the real run below reports a bad task or budget with its own message
    if gate is not None:
        print(governor.render(gate), file=sys.stderr)
        if not gate["allowed"] and not args.dry_run and not getattr(args, "force", False):
            print("lifeos: nothing was sent. Use --force to send anyway, or wait for the reset.", file=sys.stderr)
            return 4
    try:
        result = run_ask(
            home, args.model, args.task, args.budget, args.dry_run,
            full=args.full, run_id=getattr(args, "run_id", None),
        )
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(result[0])
        print(f"[dry run: about {result[1]} tokens, nothing sent]", file=sys.stderr)
    else:
        print(f"{args.model} answered; result appended to {result.relative_to(home)}")
    return 0


def cmd_delegate(args):
    home = find_home(args.home)
    try:
        out = run_delegate(home, args.task, args.model, args.budget, args.full, dry_run=args.dry_run,
                           learned=args.learned)
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    chain = " -> ".join(out.get("chain") or [])
    print(f"{out['model']}: {out['reason']}" + (f" · chain {chain}" if chain else "")
          + (" [dry run, nothing sent]" if args.dry_run else ""))
    for note in out.get("notes") or []:
        print(f"NOTE {note}")
    if out["text"]:
        print(f"\n{out['text']}\n\n[result appended to {out['path'].relative_to(home)}]")
    if out["flags"]:  # also when the answer is empty, the case CHECK exists for (a dry run has no flags)
        print("CHECK (free, no model): " + "; ".join(out["flags"]))
    return 0


def cmd_seats(args):
    home = find_home(args.home)
    rows = seats.table(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    print(json.dumps(rows, indent=2) if args.json else seats.render_table(rows))
    return 0


def cmd_review(args):
    home = find_home(args.home)
    revs = [r.strip() for r in args.reviewers.split(",") if r.strip()]
    try:
        out = run_review(
            home, args.task, reviewers=revs, budget=args.budget, dry_run=args.dry_run,
            repo=getattr(args, "repo", None), commit=getattr(args, "commit", "HEAD"),
            run_id=getattr(args, "run_id", None),
        )
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(out["pack"])
        print(f"[dry run: blind review pack ({out['sha256']}) for {', '.join(out['reviewers'])}, ~{out['tokens']} tokens]",
              file=sys.stderr)
        return 0
    commit_note = f", commit {out['commit_sha'][:12]}" if out.get("commit_sha") else ""
    print(f"blind review ({out['group_run_id']}, pack {out['sha256'][:12]}{commit_note}) -> {out['path'].relative_to(home)}")
    for r in out["results"]:
        warn = f" [CHECK: {'; '.join(r['flags'])}]" if r["flags"] else ""
        print(f"  {r['label']} ({r['run_id']}){warn}")
    return 0


def cmd_sort_csv(args):
    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
    try:
        sortcsv.require_local()
        info = sortcsv.sort_csv(args.file, args.out, args.column, cats)
    except sortcsv.Refused as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    print(f"sorted {info['rows']} rows -> {info['out']} (rules: {info['by_rule']}, local model: {info['by_model']}, "
          f"to check: {info['flagged']}). Open the file and review rows where lifeos_check is 'yes'.")
    return 0


def cmd_mcp(args):
    home = find_home(args.home)
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    mcp.serve(home, sys.stdin, sys.stdout)
    return 0


def cmd_lab(args):
    try:
        home = find_home(args.home)
    except HomeError:
        home = None
    try:
        if args.lab_action == "check":
            info = lab.check_card(home, args.card)
            c = info["card"]
            print(
                f"ok  {c['name']} v{c['version']}  prompt:{c['prompt_hash']}  "
                f"tests:{c['tests_hash']}  ~{info['tokens']} tokens/run"
            )
            return 0
        if args.lab_action == "pack":
            info = lab.pack_card(home, args.card, filled=args.filled, results_out=args.results)
            print(info["pack"], end="")
            if args.results:
                print(f"[results template written to {args.results}]", file=sys.stderr)
            return 0
        if args.lab_action == "score":
            out = lab.score_results(home, args.card, args.results, dry_run=args.dry_run)
            for r in out["per_test"]:
                verdict = "pass" if r["passed"] else "fail"
                print(f"  {r['id']}: {verdict}")
            print(f"{out['passed_count']}/5  ({out['proof_text']})")
            if out["prior_scores"]:
                print(f"earlier runs: {', '.join(out['prior_scores'])}")
            if out["same_tests_diff_prompt"]:
                print("same tests as an earlier prompt version: not independent evidence")
            print(out["score_line"])
            return 0
    except LabRefused as error:
        print(f"lifeos lab: refused ({error})", file=sys.stderr)
        return 1
    return 2



def cmd_guard(args):
    paths = staged_files() if args.staged else args.paths
    skipped = []
    results = scan_staged(paths, skipped) if args.staged else scan_paths(paths, skipped)
    blocked = 0
    for path, findings in results:
        for line, severity, kind, excerpt in findings:
            blocked += severity == "BLOCK"
            print(f"{severity:5} {path}:{line}  {kind}  {excerpt}")
    if blocked:
        print(f"\nBlocked: {blocked} finding(s) that must never enter a repo. Remove them, or mark a false alarm "
              f"with 'lifeos-guard: allow' on that line.", file=sys.stderr)
        return 1
    note = f", {len(skipped)} skipped (missing, binary or over 1 MB)" if skipped else ""
    print(f"guard ok: {len(paths) - len(skipped)} file(s) checked{note}", file=sys.stderr)
    return 0


_OK_STATES = ("available", "healthy", "cli_healthy", "resting")


def _print_provider(row):
    print(f"  {row['status']:<13} {row['model']:<10} ({row['locality']}, {row['detail']})", flush=True)


def _record_rest(home, row):
    """Save a probe that hit a usage limit, so the seat table rests it. Never spends tokens, never raises."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        saved = append_run_record(home, {
            "run_id": new_run_id(now.date()), "date": now.date().isoformat(), "command": "smoke",
            "model": row["model"], "status": "failed", "tokens": 0, "error": row["error"],
            "started_at": utc_now_iso(), "finished_at": utc_now_iso(),
        })
    except Exception:
        saved = None
    if saved is None:
        print(f"  not saved: {row['model']} is resting but logs/runs.jsonl could not be written", flush=True)


def _doctor_providers(home, args):
    """Print the provider block. Return (problems, None), or (0, exit_code) when the probe must stop."""
    smoke = bool(getattr(args, "smoke", False))
    probe = bool(getattr(args, "live", False)) or smoke
    only = {name.strip() for name in str(getattr(args, "only", "") or "").split(",") if name.strip()}
    unknown = sorted(only - set(PROVIDERS))
    if unknown:
        print(f"lifeos: unknown seat {', '.join(unknown)}; choose from {', '.join(sorted(PROVIDERS))}", file=sys.stderr)
        return 0, 2
    title = "authenticated smoke probe" if smoke else "live health probe" if probe else "binary availability"
    print(f"Providers: ({title})")
    callbacks = {}
    skip = None
    if smoke:
        print("  One tiny message per cloud seat; seats that are resting are not called.")
        skip = seats.pressure(read_run_records(home), dt.datetime.now(dt.timezone.utc))
        callbacks = {"on_start": lambda name: print(f"  probing {name} ...", file=sys.stderr, flush=True)}

        def on_row(row):
            _print_provider(row)
            if row["status"] == "resting" and row.get("error"):
                _record_rest(home, row)
        callbacks["on_row"] = on_row
    try:
        rows = provider_status(probe=probe, smoke=smoke, only=only or None, skip=skip, **callbacks)
    except KeyboardInterrupt:
        print("lifeos: stopped; the seats above were already checked.", file=sys.stderr)
        return 0, 130
    if not smoke:
        for row in rows:
            _print_provider(row)
    resting = sum(row["status"] == "resting" for row in rows)
    if resting:
        print(f"  {resting} seat(s) resting: not a fault, they reopen at the time shown.")
    return sum(row["status"] not in _OK_STATES for row in rows), None


def cmd_doctor(args):
    home = find_home(args.home)
    problems, total = 0, 0
    print(f"LifeOS home: {home}")
    for name in (*CORE_FILES, "CLAUDE.md", "AGENTS.md"):
        path = home / name
        if not path.exists():
            print(f"  missing   {name}")
            problems += name in CORE_FILES
            continue
        text = path.read_text(encoding="utf-8")
        lines, tokens = len(text.splitlines()), estimate_tokens(text)
        total += tokens if name in CORE_FILES else 0
        limit = LINE_LIMITS.get(name)
        flag = "too long" if limit and lines > limit else "ok"
        problems += flag != "ok"
        print(f"  {flag:<9} {name:<10} {lines:>3} lines  ~{tokens} tokens")
    print(f"Always-loaded core: ~{total} tokens per conversation that reads rules, me and now.")
    if total > CORE_TOKEN_CAP:
        print(f"  too big   core is ~{total} tokens, over the {CORE_TOKEN_CAP}-token cap. Trim rules, me or now.")
        problems += 1
    for name in ("ledger.csv", "proofs.csv"):
        if not (home / "logs" / name).exists():
            print(f"  missing   logs/{name}")
            problems += 1
    if getattr(args, "tools", False) or getattr(args, "live", False) or getattr(args, "smoke", False):
        found, stop = _doctor_providers(home, args)
        if stop is not None:
            return stop
        problems += found
    print("doctor: ok" if not problems else f"doctor: {problems} thing(s) to fix")
    return 0 if not problems else 1


def build_parser():
    parser = argparse.ArgumentParser(prog="lifeos", description="LifeOS Engine: tasks, weekly numbers, context packs, privacy guard.")
    parser.add_argument("--home", help="LifeOS data repo (default: LIFEOS_HOME or the current folder)")
    parser.add_argument("--version", action="version", version=f"lifeos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    task = sub.add_parser("task", help="create or list task files")
    task_sub = task.add_subparsers(dest="action", required=True)
    new = task_sub.add_parser("new", help="create a task file from one sentence")
    new.add_argument("sentence", nargs="+")
    new.add_argument("--route", default="Claude Code -> Codex review")
    new.add_argument("--level", default="L2", choices=["L0", "L1", "L2", "L3"])
    new.add_argument("--due")
    lst = task_sub.add_parser("list", help="list task files")
    lst.add_argument("--status", choices=["inbox", "doing", "done"])
    task.set_defaults(func=cmd_task)

    week = sub.add_parser("week", help="numbers for the weekly review, from the logs")
    week.add_argument("--week", help="ISO week such as 2026-W47 (default: this week)")
    week.add_argument("--json", action="store_true")
    week.add_argument("--draft", action="store_true", help="write reviews/<week>.md pre-filled with log numbers (never overwrites)")
    week.add_argument("--redteam", action="store_true", help="print a facts-only Red-Team pack for item 6 of the weekly review")
    week.set_defaults(func=cmd_week)

    ctx = sub.add_parser("context", help="print a context pack for another model, within a token budget")
    ctx.add_argument("task", nargs="?", help="task id or prefix, for example T-261116")
    ctx.add_argument("--budget", type=int, default=6000)
    ctx.add_argument("--explain", action="store_true", help="show why each file was included, trimmed or excluded, plus sha256")
    ctx.set_defaults(func=cmd_context)

    ask = sub.add_parser("ask", help="send a task's context pack to another model and write the answer back")
    ask.add_argument("model", choices=sorted(ADAPTERS))
    ask.add_argument("task", help="task id or prefix, for example T-261116")
    ask.add_argument("--budget", type=int, default=6000)
    ask.add_argument("--full", action="store_true", help="also send now.md and me.md (default: task and rules only)")
    ask.add_argument("--run-id", help="explicit run_id for idempotent retry")
    ask.add_argument("--dry-run", action="store_true", help="show the pack and token cost; send nothing")
    ask.add_argument("--force", action="store_true", help="send even if the budget governor holds the call")
    ask.set_defaults(func=cmd_ask)

    dele = sub.add_parser("delegate", help="let LifeOS pick the best-fitting model for a task, run it, and print the answer")
    dele.add_argument("task", help="task id or prefix, for example T-261116")
    dele.add_argument("--model", choices=sorted(ADAPTERS), help="override the pick")
    dele.add_argument("--budget", type=int, default=6000)
    dele.add_argument("--full", action="store_true", help="also send now.md and me.md")
    dele.add_argument("--dry-run", action="store_true", help="show which model would take it; send nothing")
    dele.add_argument("--learned", action="store_true",
                      help="use your ratings: pick the model that clearly scores best for this kind of work")
    dele.set_defaults(func=cmd_delegate)

    rate_p = sub.add_parser("rate", help="rate a model's work on a task from 1 to 5 (feeds `learn` and `delegate --learned`)")
    rate_p.add_argument("task")
    rate_p.add_argument("model")
    rate_p.add_argument("score", type=int)
    rate_p.add_argument("--note", default="")
    rate_p.set_defaults(func=cmd_rate)

    his_p = sub.add_parser("history-scan", help="scan every commit on every branch for class C data (masked output)")
    his_p.add_argument("--max-commits", type=int)
    his_p.set_defaults(func=cmd_history_scan)
    hook_p = sub.add_parser("hook", help="install the pre-commit hook that runs the guard")
    hook_sub = hook_p.add_subparsers(dest="hook_action", required=True)
    hook_ins = hook_sub.add_parser("install")
    hook_ins.add_argument("--force", action="store_true")
    hook_p.set_defaults(func=cmd_hook)

    prv_p = sub.add_parser("prove", help="run tests, guard score, outbound stop and ledger chain; write one proof file")
    prv_p.add_argument("--out")
    prv_p.add_argument("--skip-tests", action="store_true")
    prv_p.set_defaults(func=cmd_prove)
    dig_p = sub.add_parser("digest", help="Sunday review in numbers: did every part earn its place this week?")
    dig_p.add_argument("--json", action="store_true")
    dig_p.set_defaults(func=cmd_digest)

    sav_p = sub.add_parser("savings", help="tokens the context packs saved, from your own ledger")
    sav_p.add_argument("--json", action="store_true")
    sav_p.set_defaults(func=cmd_savings)
    demo_p = sub.add_parser("demo", help="60-second tour on made-up data: guard, blind panel, tamper-evident ledger, replay")
    demo_p.add_argument("--example", help="path to examples/demo-home (default: the one in the repository)")
    demo_p.add_argument("--json", action="store_true")
    demo_p.set_defaults(func=cmd_demo)

    exp_p = sub.add_parser("experiment", help="one tested rule change at a time; kept only if the numbers improve (rule 11)")
    exp_sub = exp_p.add_subparsers(dest="exp_action", required=True)
    exp_start = exp_sub.add_parser("start")
    exp_start.add_argument("change")
    exp_start.add_argument("--metric", required=True, choices=sorted(experiment.METRICS))
    exp_start.add_argument("--days", type=int, default=28)
    exp_end = exp_sub.add_parser("end")
    exp_end.add_argument("id")
    exp_sub.add_parser("list")
    exp_p.set_defaults(func=cmd_experiment)
    arch_p = sub.add_parser("arch", help="draw the module graph from the real imports (Mermaid); --check fails when docs are stale")
    arch_p.add_argument("--write", metavar="FILE")
    arch_p.add_argument("--check", metavar="FILE")
    arch_p.set_defaults(func=cmd_arch)
    pl_p = sub.add_parser("pipeline", help="run a saved flow of lifeos commands with gates (dry run unless --run)")
    pl_p.add_argument("name")
    pl_p.add_argument("--run", action="store_true")
    pl_p.set_defaults(func=cmd_pipeline)
    dc_p = sub.add_parser("decide", help="short decision records with a revisit date and an optional calibrated prediction")
    dc_sub = dc_p.add_subparsers(dest="dec_action", required=True)
    dc_add = dc_sub.add_parser("add")
    dc_add.add_argument("title")
    dc_add.add_argument("--why", required=True)
    dc_add.add_argument("--revisit", default="")
    dc_add.add_argument("--predict", default="")
    dc_add.add_argument("--p", type=int, default=70)
    dc_sub.add_parser("list")
    dc_sub.add_parser("due")
    dc_p.set_defaults(func=cmd_decide)
    bk_p = sub.add_parser("backup", help="copy logs/ with a hash manifest; --check verifies a backup")
    bk_p.add_argument("--out")
    bk_p.add_argument("--check")
    bk_p.set_defaults(func=cmd_backup)
    rd_p = sub.add_parser("redact", help="write copies of files with guard-flagged lines replaced, for sharing")
    rd_p.add_argument("files", nargs="+")
    rd_p.add_argument("--out", required=True)
    rd_p.set_defaults(func=cmd_redact)
    rl_p = sub.add_parser("release", help="read-only release plan from CHANGELOG [Unreleased]; never tags")
    rl_p.add_argument("--repo", default=".")
    rl_p.set_defaults(func=cmd_release)
    ea_p = sub.add_parser("earn", help="rule 10: did each part of the system earn its place? uses per log in the last N days")
    ea_p.add_argument("--days", type=int, default=30)
    ea_p.set_defaults(func=cmd_earn)
    td_p = sub.add_parser("today", help="one screen for the day: next task, due decisions and words, open predictions, experiment")
    td_p.set_defaults(func=cmd_today)
    li_p = sub.add_parser("lint", help="check task files: front matter, done_when, level, status, due, proof on done tasks")
    li_p.set_defaults(func=cmd_lint)
    sl_p = sub.add_parser("stale", help="open tasks, unresolved predictions and due decisions older than N days")
    sl_p.add_argument("--days", type=int, default=14)
    sl_p.set_defaults(func=cmd_stale)
    sc_p = sub.add_parser("schema", help="the format of every log and file the engine writes, generated from the code")
    sc_p.add_argument("--write")
    sc_p.add_argument("--check")
    sc_p.set_defaults(func=cmd_schema)
    st_p = sub.add_parser("selftest", help="run the commands on a throwaway copy of the demo home; PASS or FAIL for each")
    st_p.add_argument("--example", help="path to examples/demo-home (default: the one in the repository)")
    st_p.set_defaults(func=cmd_selftest)

    num_p = sub.add_parser("numbers", help="one page of checkable facts: code, tests, guard score, ledger (counts only)")
    num_p.add_argument("--out", help="write the page to this file")
    num_p.add_argument("--html", help="write a self-contained HTML page (no script, no links) to this file")
    num_p.add_argument("--json", action="store_true")
    num_p.set_defaults(func=cmd_numbers)

    mis_p = sub.add_parser("mistakes", help="quiz yourself on the verified questions you missed most")
    mis_p.add_argument("--count", type=int, default=5)
    mis_p.add_argument("--json", action="store_true")
    mis_p.set_defaults(func=cmd_mistakes)
    voc_p = sub.add_parser("vocab", help="your own German words: add, quiz, answer (local only, no model)")
    voc_sub = voc_p.add_subparsers(dest="vocab_action", required=True)
    voc_add = voc_sub.add_parser("add")
    voc_add.add_argument("word")
    voc_add.add_argument("meaning")
    voc_add.add_argument("--example", default="")
    voc_quiz = voc_sub.add_parser("quiz")
    voc_quiz.add_argument("--count", type=int, default=10)
    voc_quiz.add_argument("--reveal", action="store_true")
    voc_ans = voc_sub.add_parser("answer")
    voc_ans.add_argument("word")
    voc_ans.add_argument("result", choices=["good", "again"])
    voc_p.set_defaults(func=cmd_vocab)

    pre_p = sub.add_parser("predict", help="write down what you expect and how sure you are (1-99 %), before you know")
    pre_p.add_argument("claim")
    pre_p.add_argument("--p", type=int, required=True, help="probability in percent, 1 to 99")
    pre_p.set_defaults(func=cmd_predict)
    res_p = sub.add_parser("resolve", help="record what happened to a prediction")
    res_p.add_argument("id")
    res_p.add_argument("outcome", choices=["yes", "no"])
    res_p.set_defaults(func=cmd_resolve)
    cal_p = sub.add_parser("calibration", help="Brier score and confidence bands from your resolved predictions")
    cal_p.add_argument("--json", action="store_true")
    cal_p.set_defaults(func=cmd_calibration)

    learn_p = sub.add_parser("learn", help="show your ratings per kind of work and which model scores best")
    learn_p.add_argument("--json", action="store_true")
    learn_p.set_defaults(func=cmd_learn)

    rev = sub.add_parser("review", help="run an independent blind review (rule 7) across multiple models")
    rev.add_argument("task", help="task id or prefix, for example T-261116")
    rev.add_argument("--reviewers", default="codex,claude", help="comma-separated reviewer models (default: codex,claude)")
    rev.add_argument("--repo", help="git repository path to inspect and mount in an isolated read-only worktree")
    rev.add_argument("--commit", default="HEAD", help="git commit or ref to review when --repo is set (default: HEAD)")
    rev.add_argument("--run-id", help="explicit parent run_id for idempotent retry")
    rev.add_argument("--budget", type=int, default=6000)
    rev.add_argument("--dry-run", action="store_true", help="show the blind review pack and hash; send nothing")
    rev.set_defaults(func=cmd_review)

    srt = sub.add_parser("sort-csv", help="add a spending category to a bank CSV, fully local (Ollama), never in a repo")
    srt.add_argument("file")
    srt.add_argument("--out", help="default: <file>.sorted.csv beside the input")
    srt.add_argument("--column", help="the text column (default: found by name)")
    srt.add_argument("--categories", help="comma separated; default: groceries,rent,transport,...")
    srt.set_defaults(func=cmd_sort_csv)

    serve = sub.add_parser("mcp", help="run a local MCP server so chat apps can read and write task files")
    serve.set_defaults(func=cmd_mcp)

    guard = sub.add_parser("guard", help="block class C data before it enters a repo")
    guard.add_argument("paths", nargs="*")
    guard.add_argument("--staged", action="store_true", help="check the files staged for commit")
    guard.set_defaults(func=cmd_guard)

    doctor = sub.add_parser("doctor", help="check the data repo and the token cost of its core files")
    doctor.add_argument("--tools", action="store_true", help="check binary availability of local and remote model CLIs")
    doctor.add_argument("--live", action="store_true", help="probe live provider health (local Ollama tags and CLI --version)")
    doctor.add_argument("--smoke", action="store_true", help="run an authenticated live smoke request per provider")
    doctor.add_argument("--only", help="with --smoke or --live: probe only these seats, comma separated (saves usage)")
    doctor.set_defaults(func=cmd_doctor)

    lab_p = sub.add_parser("lab", help="Prompt Lab: validate cards, pack test inputs, and score results offline")
    lab_sub = lab_p.add_subparsers(dest="lab_action", required=True)
    lab_chk = lab_sub.add_parser("check", help="validate a prompt card and print its prompt and tests hashes")
    lab_chk.add_argument("card", help="card path or name in prompts/cards/")
    lab_pck = lab_sub.add_parser("pack", help="print the card's prompt and five test inputs")
    lab_pck.add_argument("card", help="card path or name in prompts/cards/")
    lab_pck.add_argument("--filled", action="store_true", help="print five finished prompts instead")
    lab_pck.add_argument("--results", help="write the empty results file with locked hashes (never overwrites)")
    lab_scr = lab_sub.add_parser("score", help="score a results file offline and log one proof row")
    lab_scr.add_argument("card", help="card path or name in prompts/cards/")
    lab_scr.add_argument("results", help="results file path")
    lab_scr.add_argument("--dry-run", action="store_true", help="score without writing to logs/proofs.csv")
    lab_p.set_defaults(func=cmd_lab)

    log_p = sub.add_parser("log", help="append a validated row to proofs.csv, ledger.csv, health.csv, or hours.csv")
    log_sub = log_p.add_subparsers(dest="log_action", required=True)
    log_prf = log_sub.add_parser("proof", help="append a proof row to logs/proofs.csv")
    log_prf.add_argument("--area", required=True)
    log_prf.add_argument("--proof", required=True)
    log_prf.add_argument("--link", required=True)
    log_prf.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_ldg = log_sub.add_parser("ledger", help="append a ledger row to logs/ledger.csv")
    log_ldg.add_argument("--task", required=True)
    log_ldg.add_argument("--model", required=True)
    log_ldg.add_argument("--minutes", required=True)
    log_ldg.add_argument("--note", required=True)
    log_ldg.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_hlt = log_sub.add_parser("health", help="append a daily health row to logs/health.csv")
    log_hlt.add_argument("--sleep", required=True)
    log_hlt.add_argument("--gym", required=True)
    log_hlt.add_argument("--energy", required=True)
    log_hlt.add_argument("--note", default="")
    log_hlt.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_hrs = log_sub.add_parser("hours", help="append a study/work hours row to logs/hours.csv")
    log_hrs.add_argument("--area", required=True)
    log_hrs.add_argument("--hours", required=True)
    log_hrs.add_argument("--note", default="")
    log_hrs.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_p.set_defaults(func=cmd_log)

    runs_p = sub.add_parser("runs", help="inspect execution run records and summary analytics from logs/runs.jsonl")
    runs_p.add_argument("--status", help="filter by terminal status (ok, failed, timeout, blocked, tool_missing, partial)")
    runs_p.add_argument("--model", help="filter by provider model name")
    runs_p.add_argument("--task", help="filter by task id or prefix")
    runs_p.add_argument("--limit", type=int, default=20, help="max recent records to display (default: 20)")
    runs_p.add_argument("--json", action="store_true", help="output structured JSON summary and records")
    runs_p.set_defaults(func=cmd_runs)

    ver_p = sub.add_parser("verify", help="prove logs/runs.jsonl was not edited, reordered or cut (hash chain)")
    ver_p.add_argument("--anchor", help="a head hash you saved earlier; checks the log still contains that exact state")
    ver_p.add_argument("--json", action="store_true", help="output structured JSON")
    ver_p.set_defaults(func=cmd_verify)

    rpl_p = sub.add_parser("replay", help="rebuild an ask run's context from today's files and prove it is the same input")
    rpl_p.add_argument("run_id")
    rpl_p.add_argument("--json", action="store_true", help="output structured JSON")
    rpl_p.set_defaults(func=cmd_replay)

    can_p = sub.add_parser("canary", help="guard score on generated fake identifiers, and proof ask never sends them")
    can_p.add_argument("--json", action="store_true", help="output structured JSON")
    can_p.set_defaults(func=cmd_canary)

    pan_p = sub.add_parser("panel", help="ask two to four models the same task blind, then report where they disagree")
    pan_p.add_argument("task")
    pan_p.add_argument("--models", required=True, help="comma-separated, for example claude,codex,gemini")
    pan_p.add_argument("--budget", type=int, default=6000)
    pan_p.add_argument("--full", action="store_true", help="also send now.md and me.md")
    pan_p.add_argument("--json", action="store_true")
    pan_p.set_defaults(func=cmd_panel)

    kzn_p = sub.add_parser("kaizen", help="monthly System Health check (Section 10.3) and 4-week trial audit")
    kzn_p.add_argument("--month", help="YYYY-MM (default: current month)")
    kzn_p.add_argument("--draft", action="store_true", help="write reviews/<YYYY-MM>.md without overwriting")
    kzn_p.add_argument("--json", action="store_true", help="output structured JSON health report")
    kzn_p.set_defaults(func=cmd_kaizen)

    rte_p = sub.add_parser("route", help="evaluate the 6-question Section 8.2 routing decision for a task or prompt")
    rte_p.add_argument("target", nargs="+", help="task id (e.g. T-261116) or free-text task description")
    rte_p.add_argument("--tier", help="override 5-tier data classification (PUBLIC, INTERNAL, PERSONAL, SENSITIVE, SECRET)")
    rte_p.add_argument("--full", action="store_true", help="evaluate with me.md and now.md included")
    rte_p.add_argument("--json", action="store_true", help="output structured JSON routing decision")
    rte_p.set_defaults(func=cmd_route)

    seat_p = sub.add_parser("seats", help="show every model seat: 7-day spend against its one limit, rest, and replacement")
    seat_p.add_argument("--json", action="store_true", help="output the seat table as JSON")
    seat_p.set_defaults(func=cmd_seats)

    ckp_p = sub.add_parser("cockpit", help="export or serve the learning-first LifeOS Cockpit (#focus, #library, #recall, #mastery)")
    ckp_p.add_argument("--export", help="output HTML file path (default: <home>/cockpit/index.html)")
    ckp_p.add_argument("--serve", action="store_true", help="run a local HTTP server bound strictly to 127.0.0.1")
    ckp_p.add_argument("--port", type=int, default=8765, help="localhost port for --serve (default: 8765)")
    ckp_p.set_defaults(func=cmd_cockpit)

    std_p = sub.add_parser("study", help="local-first notes, grounded question banks, retrieval practice and exams")
    std_sub = std_p.add_subparsers(dest="study_action", required=True)
    std_src = std_sub.add_parser("sources", help="list indexed Markdown/text learning sources")
    std_src.add_argument("--json", action="store_true")
    std_imp = std_sub.add_parser("import", help="copy a UTF-8 Markdown/text file into the guarded source library")
    std_imp.add_argument("file")
    std_imp.add_argument("--title")
    std_imp.add_argument("--subject", default="general")
    std_imp.add_argument("--source-url", default="")
    std_bnk = std_sub.add_parser("bank", help="create a grounded draft question bank from one learning source")
    std_bnk.add_argument("source", help="LifeOS-relative source path, for example learning/sources/python.md")
    std_bnk.add_argument("--overwrite", action="store_true")
    std_cur = std_sub.add_parser("curricula", help="list ordered learning journeys and their source steps")
    std_ref = std_sub.add_parser("refresh", help="create missing grounded banks for curriculum sources")
    std_ref.add_argument("--curriculum", help="optional curriculum id")
    std_sub.add_parser("gaps", help="show sanitized weak concepts and their remediation sources")
    std_ver = std_sub.add_parser("verify", help="record human trust state for one grounded question")
    std_ver.add_argument("bank")
    std_ver.add_argument("question")
    std_ver.add_argument("--trust", choices=study.TRUST_STATES, default="verified")
    std_att = std_sub.add_parser("attempt", help="record a verified retrieval attempt and next-review interval")
    std_att.add_argument("question")
    std_att.add_argument("--rating", choices=study.RATINGS, required=True)
    std_att.add_argument("--seconds", type=int, default=0)
    std_exm = std_sub.add_parser("exam", help="compose a printable exam plus separate key from verified questions")
    std_exm.add_argument("--title", default="Practice Exam")
    std_exm.add_argument("--subject")
    std_exm.add_argument("--count", type=int, default=10)
    std_exm.add_argument("--minutes", type=int, default=60)
    std_p.set_defaults(func=cmd_study)

    exm_p = sub.add_parser("exam", help="generate or score a 60-90 min Monthly No-AI Exam (Section 13.4 & Appendix B8)")
    exm_p.add_argument("--month", help="YYYY-MM (default: current month)")
    exm_p.add_argument("--module", default="CSEBDSDSSE01 · Data Science Software Engineering", help="IU module focus")
    exm_p.add_argument("--draft", action="store_true", help="write reviews/exam-<YYYY-MM>.md")
    exm_p.add_argument("--overwrite", action="store_true", help="overwrite existing exam draft")
    exm_p.add_argument("--score-skill", help="skill name in logs/skills.md to record a graded no-AI exam score")
    exm_p.add_argument("--score-pct", type=int, default=0, help="exam score percentage (0-100); >=80 elevates level to 3")
    exm_p.add_argument("--link", help="proof link for logs/proofs.csv")
    exm_p.set_defaults(func=cmd_exam)

    bkf_p = sub.add_parser("bakeoff", help="generate or score a blind Role Bake-Off scorecard (Section 10.4 & Appendix A8)")
    bkf_p.add_argument("--quarter", help="YYYY-Q1..Q4 (default: current quarter)")
    bkf_p.add_argument("--task-type", default="Decision Memo", help="task category being compared")
    bkf_p.add_argument("--model-a", default="claude")
    bkf_p.add_argument("--model-b", default="chatgpt")
    bkf_p.add_argument("--scores", help="JSON dict of X/Y task scores to unseal winner")
    bkf_p.add_argument("--draft", action="store_true", help="write reviews/bakeoff-<quarter>-<slug>.md")
    bkf_p.add_argument("--overwrite", action="store_true")
    bkf_p.set_defaults(func=cmd_bakeoff)

    shw_p = sub.add_parser("showcase", help="draft a 20-minute Build-in-Public weekly proof post & case study (Section 14.4 / D12)")
    shw_p.add_argument("--week", help="ISO week such as 2026-W46")
    shw_p.add_argument("--draft", action="store_true", help="write reviews/post-<week>.md")
    shw_p.add_argument("--overwrite", action="store_true")
    shw_p.set_defaults(func=cmd_showcase)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (HomeError, FileNotFoundError, ValueError) as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
