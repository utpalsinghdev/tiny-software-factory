"""Tests for factory/bin/dashboard read_job / read_jobs."""
import contextlib
import importlib.machinery
import io
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY

# Load dashboard script without importing as a package
_DASH_PATH = Path(__file__).resolve().parents[2] / "factory" / "bin" / "dashboard"
_loader = importlib.machinery.SourceFileLoader("dashboard", str(_DASH_PATH))
_spec = importlib.util.spec_from_loader("dashboard", _loader)
dash = importlib.util.module_from_spec(_spec)
_loader.exec_module(dash)


def make_job(root, stage="intake", round=1, reviewers=None, rounds=None, files=None):
    """Write a minimal job folder and return its path."""
    if reviewers is None:
        reviewers = ["code-review"]
    if rounds is None:
        rounds = {}
    if files is None:
        files = {}

    # job id: use a stable name so tests are predictable
    job_id = f"001-test-job"
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # job.json shape mirrors bin/job cmd_create
    job = {
        "id": job_id,
        "issue": 1,
        "title": "Test job",
        "issue_url": "https://github.com/owner/repo/issues/1",
        "pr": None,
        "pr_url": None,
        "branch": f"factory/{job_id}",
        "worktree": str(root / ".worktrees" / job_id),
        "stage": stage,
        "round": round,
        "round_limit": 3,
        "intake": None,
        "reviewers": reviewers,
        "reviews": {},
        "started": "2024-01-01T00:00:00Z",
        "ended": None,
    }
    (job_dir / "job.json").write_text(json.dumps(job, indent=2) + "\n")

    # write round review files
    for rn, reviewer_verdicts in rounds.items():
        rd = job_dir / f"round-{rn}"
        rd.mkdir(exist_ok=True)
        for reviewer, verdict in reviewer_verdicts.items():
            (rd / f"{reviewer}.md").write_text(f"VERDICT: {verdict}\n\nSome details.")

    # extra files
    for name, content in files.items():
        p = job_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    # write canonical intake.md so at/mtime works, unless caller provided it
    if "intake.md" not in files:
        (job_dir / "intake.md").write_text("# Intake\n\nSome intake content.")

    return job_dir


class TestReadJob(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_two_failed_rounds_stay_separate(self):
        job_dir = make_job(
            self.tmp,
            stage="build",
            round=3,
            reviewers=["code-review", "ui-ux-review"],
            rounds={
                1: {"code-review": "CHANGES", "ui-ux-review": "PASS"},
                2: {"code-review": "CHANGES"},
            },
        )
        # create build.md so build stage has an mtime
        (job_dir / "build.md").write_text("# Build\n\nBuild notes.")
        v = dash.read_job(job_dir)
        # round 3 is empty while the builder works, so it is not shown
        assert [r["n"] for r in v["rounds"]] == [1, 2]
        assert v["rounds"][1]["reviews"] == {"code-review": "CHANGES", "ui-ux-review": "missing"}
        assert not any(r["current"] for r in v["rounds"])
        assert [t["state"] for t in v["timeline"]][:4] == ["done", "done", "current", "todo"]

    def test_needs_human_shows_reason(self):
        # needs-human after build: intake done, spec done, build done, then exit
        job_dir = make_job(
            self.tmp,
            stage="needs-human",
            files={"decision.md": "ESCALATE\n\n## Why\nconflict",
                   "spec.md": "# Spec\n\nSpec content.",
                   "build.md": "# Build\n\nBuild content."},
        )
        v = dash.read_job(job_dir)
        assert v["needs"] == "you" and "conflict" in v["note"]
        tl = v["timeline"]
        assert tl[-1] == {"stage": "needs-human", "state": "exit", "at": ANY}
        # intake, spec, build must all be done
        by_stage = {t["stage"]: t["state"] for t in tl}
        assert by_stage["intake"] == "done"
        assert by_stage["spec"] == "done"
        assert by_stage["build"] == "done"
        # review and approve must NOT appear (replaced by exit)
        assert "review" not in by_stage
        assert "approve" not in by_stage

    def test_merging_timeline(self):
        job_dir = make_job(self.tmp, stage="merging",
                           files={"spec.md": "s", "build.md": "b", "decision.md": "APPROVE\n\nok"},
                           rounds={1: {"code-review": "PASS"}})
        states = {t["stage"]: t["state"] for t in dash.read_job(job_dir)["timeline"]}
        assert states == {"intake": "done", "spec": "done", "build": "done",
                          "review": "done", "approve": "done", "merged": "current"}

    def test_build_blocked_needs_human_empty_round_stops_at_build(self):
        job_dir = make_job(self.tmp, stage="needs-human",
                           files={"spec.md": "s", "build.md": "STATUS: BLOCKED\n\nx",
                                  "decision.md": "ESCALATE\n\nblocked"})
        (job_dir / "round-1").mkdir()
        tl = dash.read_job(job_dir)["timeline"]
        assert [(t["stage"], t["state"]) for t in tl] == [
            ("intake", "done"), ("spec", "done"), ("build", "done"), ("needs-human", "exit")]

    def test_build_round_one_empty_shows_not_started(self):
        job_dir = make_job(self.tmp, stage="build", files={"spec.md": "s"})
        (job_dir / "round-1").mkdir()
        v = dash.read_job(job_dir)
        assert v["rounds"] == []
        html = dash.render([v], "2024-01-01T12:00:00Z", None)
        self.assertIn("Not started", html)
        self.assertNotIn("Pending", html)

    def test_lowercase_verdict_is_invalid(self):
        job_dir = make_job(self.tmp, stage="review", rounds={1: {"code-review": "PASS"}})
        (job_dir / "round-1" / "code-review.md").write_text("verdict: pass\n")
        assert dash.read_job(job_dir)["rounds"][0]["reviews"]["code-review"] == "invalid"
        (job_dir / "round-1" / "code-review.md").write_text("VERDICT: PASS, mostly\n")
        assert dash.read_job(job_dir)["rounds"][0]["reviews"]["code-review"] == "invalid"

    def test_non_object_job_json_is_unreadable(self):
        (self.tmp / "009-list").mkdir()
        (self.tmp / "009-list" / "job.json").write_text("[1, 2]")
        result = dash.read_jobs(self.tmp)
        assert result[0]["error"] and "not an object" in result[0]["error"]

    def test_unreadable_job_is_reported_not_raised(self):
        (self.tmp / "007-x").mkdir()
        (self.tmp / "007-x" / "job.json").write_text("{")
        result = dash.read_jobs(self.tmp)
        assert len(result) == 1
        assert result[0]["error"]

    def test_missing_jobs_dir(self):
        assert dash.read_jobs(self.tmp / "nope") == []

    def test_needs_info_shows_intake_note(self):
        # needs-info from intake: intake done, then exit
        job_dir = make_job(
            self.tmp,
            stage="needs-info",
            files={"intake.md": "# Intake\n\nPlease clarify the requirements."},
        )
        v = dash.read_job(job_dir)
        assert v["needs"] == "author"
        assert "clarify" in v["note"]
        tl = v["timeline"]
        by_stage = {t["stage"]: t["state"] for t in tl}
        assert by_stage["intake"] == "done"
        assert tl[-1] == {"stage": "needs-info", "state": "exit", "at": ANY}
        assert "spec" not in by_stage

    def test_rejected_at_intake_timeline(self):
        # rejected from intake: intake done, then exit
        job_dir = make_job(
            self.tmp,
            stage="rejected",
            files={"rejection.md": "# Rejected\n\nNot a good fit."},
        )
        v = dash.read_job(job_dir)
        assert v["note"] is not None and "fit" in v["note"]
        tl = v["timeline"]
        by_stage = {t["stage"]: t["state"] for t in tl}
        assert by_stage["intake"] == "done"
        assert tl[-1] == {"stage": "rejected", "state": "exit", "at": ANY}
        assert "spec" not in by_stage

    def test_basic_intake_stage(self):
        job_dir = make_job(self.tmp, stage="intake", round=0)
        v = dash.read_job(job_dir)
        assert v["id"] == "001-test-job"
        assert v["stage"] == "intake"
        assert v["error"] is None
        assert v["needs"] is None
        assert v["note"] is None
        # timeline: intake=current, rest=todo
        states = [t["state"] for t in v["timeline"]]
        assert states[0] == "current"
        assert all(s == "todo" for s in states[1:])

    def test_read_jobs_sorted_by_id(self):
        # create two jobs
        for jid in ["002-beta", "001-alpha"]:
            d = self.tmp / jid
            d.mkdir()
            job = {
                "id": jid, "issue": 1, "title": "T", "issue_url": "u",
                "pr": None, "pr_url": None, "branch": "b", "worktree": "w",
                "stage": "intake", "round": 0, "round_limit": 3,
                "intake": None, "reviewers": [], "reviews": {},
                "started": "2024-01-01T00:00:00Z", "ended": None,
            }
            (d / "job.json").write_text(json.dumps(job))
        jobs = dash.read_jobs(self.tmp)
        assert [j["id"] for j in jobs] == ["001-alpha", "002-beta"]


class TestPrChecks(unittest.TestCase):
    """Tests for pr_checks()."""

    def _run(self, stdout, returncode=0):
        """Return a fake subprocess.run that returns a SimpleNamespace."""
        from types import SimpleNamespace

        def fake_run(cmd, **kwargs):
            return SimpleNamespace(stdout=stdout, returncode=returncode)

        return fake_run

    def test_none_pr_returns_none(self):
        result = dash.pr_checks(None)
        assert result is None

    def test_pass_fail_skipping_returncode_1(self):
        payload = json.dumps([
            {"name": "lint",   "bucket": "pass",     "link": "https://ci/1"},
            {"name": "deploy", "bucket": "fail",     "link": "https://ci/2"},
            {"name": "skip",   "bucket": "skipping", "link": "https://ci/3"},
        ])
        result = dash.pr_checks(42, run=self._run(payload, returncode=1))
        assert result["passed"] == 1
        assert result["total"] == 2   # skipping excluded
        assert result["ok"] is True   # all non-skip that ran: 1 pass, 1 fail -> ok per spec?
        # ok is True because we got a valid response (gh exit 1 is normal)
        assert len(result["checks"]) == 3

    def test_runs_gh_in_repo(self):
        seen = {}
        def fake_run(cmd, **kwargs):
            seen.update(kwargs)
            from types import SimpleNamespace
            return SimpleNamespace(stdout="[]", returncode=0)
        dash.pr_checks(1, run=fake_run)
        assert seen["cwd"] == dash.REPO

    def test_empty_list_means_no_checks(self):
        for out in ("[]", ""):
            result = dash.pr_checks(42, run=self._run(out, returncode=1))
            assert result["ok"] is True and result["checks"] == []
        html = dash.render([TestRender._view(None, pr=42, checks=result)], "2024-01-01T12:00:00Z", None)
        self.assertIn("No checks", html)
        self.assertNotIn("Checks unavailable", html)

    def test_non_dict_items_skipped(self):
        payload = json.dumps(["junk", 3, {"name": "lint", "bucket": "pass", "link": ""}])
        result = dash.pr_checks(42, run=self._run(payload))
        assert [c["name"] for c in result["checks"]] == ["lint"]

    def test_file_not_found_returns_error_dict(self):
        def raising_run(cmd, **kwargs):
            raise FileNotFoundError("gh not found")

        result = dash.pr_checks(42, run=raising_run)
        assert result["ok"] is False
        assert result["checks"] == []
        assert result["passed"] == 0
        assert result["total"] == 0


class TestRender(unittest.TestCase):
    NOW = "2024-01-01T12:00:00Z"

    def _view(self, **overrides):
        base = {
            "id": "001-test",
            "issue": 1,
            "title": "Test job",
            "issue_url": "https://github.com/owner/repo/issues/1",
            "pr": None,
            "pr_url": None,
            "stage": "intake",
            "round": 0,
            "round_limit": 3,
            "started": "2024-01-01T00:00:00Z",
            "ended": None,
            "error": None,
            "needs": None,
            "note": None,
            "required": [],
            "rounds": [],
            "timeline": [],
            "checks": None,
        }
        base.update(overrides)
        return base

    def test_empty_jobs_shows_placeholder(self):
        html = dash.render([], self.NOW, None)
        self.assertIn("No jobs yet", html)

    def test_xss_title_escaped(self):
        view = self._view(title='<script>alert(1)</script>')
        html = dash.render([view], self.NOW, None)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_reviews_count_current_round(self):
        rounds = [
            {"n": 1, "reviews": {"alice": "PASS", "bob": "CHANGES", "carol": "pending"}, "current": True},
        ]
        view = self._view(required=["alice", "bob", "carol"], rounds=rounds, stage="review")
        html = dash.render([view], self.NOW, None)
        self.assertIn("1 of 3 passed", html)

    def test_refresh_adds_meta_tag(self):
        html = dash.render([], self.NOW, 5)
        self.assertIn('content="5"', html)

    def test_no_refresh_no_meta_tag(self):
        html = dash.render([], self.NOW, None)
        self.assertNotIn('http-equiv="refresh"', html)

    # Fix round 1 tests

    def test_card_shows_issue_number(self):
        view = self._view(issue=42, issue_url="https://github.com/owner/repo/issues/42")
        html = dash.render([view], self.NOW, None)
        self.assertIn("#42", html)

    def test_card_shows_job_id(self):
        view = self._view(id="007-my-job")
        html = dash.render([view], self.NOW, None)
        self.assertIn("007-my-job", html)

    def test_per_check_colours(self):
        checks = {
            "ok": True,
            "passed": 1,
            "total": 3,
            "checks": [
                {"name": "lint", "bucket": "pass", "link": ""},
                {"name": "test", "bucket": "fail", "link": ""},
                {"name": "deploy", "bucket": "pending", "link": ""},
            ],
        }
        view = self._view(checks=checks)
        html = dash.render([view], self.NOW, None)
        # Summary must be red when any fail
        self.assertIn("checks-fail", html)
        # Individual check classes present
        self.assertIn("check-pass", html)
        self.assertIn("check-fail", html)
        self.assertIn("check-pending", html)

    def test_checks_summary_amber_when_pending_no_fail(self):
        checks = {
            "ok": True,
            "passed": 1,
            "total": 2,
            "checks": [
                {"name": "lint", "bucket": "pass", "link": ""},
                {"name": "test", "bucket": "pending", "link": ""},
            ],
        }
        view = self._view(checks=checks)
        html = dash.render([view], self.NOW, None)
        self.assertIn('class="checks checks-pending"', html)
        self.assertNotIn('class="checks checks-fail"', html)

    def test_rejected_and_merged_classes(self):
        tl_m = [{"stage": "merged", "state": "current", "at": None}]
        tl_r = [{"stage": "rejected", "state": "exit", "at": None}]
        html = dash.render([self._view(stage="merged", timeline=tl_m)], self.NOW, None)
        self.assertIn('class="st st-merged"', html)
        html = dash.render([self._view(stage="rejected", timeline=tl_r)], self.NOW, None)
        self.assertIn('class="st st-exit x-fail"', html)

    def test_needs_you_and_needs_wait_card_classes(self):
        html = dash.render([self._view(stage="needs-human", needs="you", note="why")], self.NOW, None)
        self.assertIn('class="job needs-you"', html)
        self.assertIn('class="note n-you"', html)
        html = dash.render([self._view(stage="needs-info", needs="author", note="what")], self.NOW, None)
        self.assertIn('class="job needs-wait"', html)
        self.assertIn('class="note n-wait"', html)

    def test_pr_without_fetched_checks(self):
        view = self._view(stage="review", pr=7, pr_url="https://github.com/o/r/pull/7")
        del view["checks"]
        html = dash.render([view], self.NOW, None)
        self.assertIn('href="https://github.com/o/r/pull/7"', html)
        self.assertIn("Checks not fetched (--no-gh)", html)
        self.assertNotIn("No PR yet", html)

    def test_no_empty_status_block(self):
        view = self._view()
        del view["checks"]
        html = dash.render([view], self.NOW, None)
        self.assertNotIn('<div class="status"></div>', html)

    def test_note_strips_heading_markers(self):
        view = self._view(note="## Why\nSome reason\n### Detail")
        html = dash.render([view], self.NOW, None)
        # Heading markers stripped
        self.assertNotIn("## Why", html)
        self.assertNotIn("### Detail", html)
        # Content still present (escaped)
        self.assertIn("Why", html)
        self.assertIn("Some reason", html)
        self.assertIn("Detail", html)

    def test_fmt_elapsed_minutes_only(self):
        result = dash._fmt_elapsed("2024-01-01T00:00:00Z", "2024-01-01T00:35:00Z", "2024-01-01T12:00:00Z")
        self.assertEqual(result, "35m")

    def test_fmt_elapsed_hours_and_minutes(self):
        result = dash._fmt_elapsed("2024-01-01T00:00:00Z", "2024-01-01T02:30:00Z", "2024-01-01T12:00:00Z")
        self.assertEqual(result, "2h30m")

    def test_fmt_elapsed_zero_minutes(self):
        result = dash._fmt_elapsed("2024-01-01T00:00:00Z", "2024-01-01T00:00:45Z", "2024-01-01T12:00:00Z")
        self.assertEqual(result, "0m")


    def test_fmt_elapsed_pads_minutes_with_hours(self):
        result = dash._fmt_elapsed("2024-01-01T00:00:00Z", "2024-01-01T02:05:00Z", self.NOW)
        self.assertEqual(result, "2h05m")

    def test_sections_in_order_and_empty_groups_hidden(self):
        views = [
            self._view(id="d", stage="merged"),
            self._view(id="m", stage="build"),
            self._view(id="y", stage="needs-human", needs="you"),
        ]
        html = dash.render(views, self.NOW, None)
        iy, im, idn = (html.index(f">{h}</h2>") for h in ("Needs you", "Moving", "Done"))
        self.assertTrue(iy < im < idn)
        self.assertNotIn(">Waiting on the author</h2>", html)
        views.append(self._view(id="a", stage="needs-info", needs="author"))
        html = dash.render(views, self.NOW, None)
        ia = html.index(">Waiting on the author</h2>")
        self.assertTrue(html.index(">Needs you</h2>") < ia < html.index(">Moving</h2>"))

    def test_line_current_and_exit(self):
        tl = [{"stage": "intake", "state": "done", "at": None},
              {"stage": "spec", "state": "current", "at": None},
              {"stage": "build", "state": "todo", "at": None}]
        html = dash.render([self._view(stage="spec", timeline=tl)], self.NOW, None)
        self.assertIn('aria-label="Stages"', html)
        self.assertRegex(html, r'<li class="st st-current"[^>]*aria-current="step"')
        tl = [{"stage": "intake", "state": "done", "at": None},
              {"stage": "needs-human", "state": "exit", "at": None}]
        html = dash.render([self._view(stage="needs-human", needs="you", timeline=tl)], self.NOW, None)
        line = html[html.index('<ol class="line'):]
        line = line[:line.index("</ol>")]
        self.assertRegex(line, r'<li class="st st-exit[^"]*"[^>]*>.*</li>\s*$')

    def test_page_hygiene(self):
        html = dash.render([self._view(stage="build")], self.NOW, 5)
        self.assertNotIn("<script", html)
        self.assertNotIn("transition: all", html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn("prefers-color-scheme", html)

    def test_no_all_caps_stage_labels(self):
        tl = [{"stage": "intake", "state": "done", "at": None},
              {"stage": "needs-human", "state": "exit", "at": None}]
        html = dash.render([self._view(stage="needs-human", needs="you", timeline=tl)], self.NOW, None)
        self.assertIn("Needs you", html)
        self.assertNotIn("NEEDS-HUMAN", html)
        self.assertNotIn("text-transform: uppercase", html)


class TestMain(unittest.TestCase):
    """CLI integration tests for main()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir()
        make_job(self.jobs_dir, stage="build")
        self.out = self.root / "out" / "dashboard.html"

    def tearDown(self):
        self.tmp.cleanup()

    def _run_main(self, extra_args=()):
        import unittest.mock as mock
        with mock.patch.object(dash, "JOBS", self.jobs_dir), \
             mock.patch.object(dash, "CONFIG_PATH", self.root / "config.json"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                dash.main(["--out", str(self.out), "--no-gh"] + list(extra_args))
            self.assertEqual(buf.getvalue().strip(), str(self.out))

    def test_writes_html_with_job_id(self):
        self._run_main()
        self.assertTrue(self.out.exists())
        content = self.out.read_text()
        self.assertIn("001-test-job", content)

    def test_no_jobs_dir_exits_zero_says_no_jobs(self):
        import unittest.mock as mock
        missing = self.root / "nonexistent-jobs"
        with mock.patch.object(dash, "JOBS", missing), \
             mock.patch.object(dash, "CONFIG_PATH", self.root / "config.json"):
            with contextlib.redirect_stdout(io.StringIO()):
                dash.main(["--out", str(self.out), "--no-gh"])
        self.assertIn("No jobs", self.out.read_text())

    def test_fixture_tree_unchanged_after_main(self):
        """main() must not create or modify any file under JOBS."""
        def snapshot(d):
            return {str(p.relative_to(d)): p.stat().st_mtime for p in d.rglob("*")}
        before = snapshot(self.jobs_dir)
        self._run_main()
        after = snapshot(self.jobs_dir)
        self.assertEqual(before, after)

    def test_atomic_write_via_tmp(self):
        """Output is written atomically: no .tmp file left behind."""
        self._run_main()
        self.assertFalse(self.out.with_suffix(".tmp").exists())

    def test_refresh_meta_with_watch_arg(self):
        """--watch N sets the refresh meta tag in the HTML."""
        import unittest.mock as mock
        # Patch sleep so the loop exits immediately after one iteration
        call_count = [0]
        def fake_sleep(n):
            call_count[0] += 1
            raise KeyboardInterrupt
        with mock.patch.object(dash, "JOBS", self.jobs_dir), \
             mock.patch.object(dash, "CONFIG_PATH", self.root / "config.json"), \
             mock.patch("time.sleep", fake_sleep):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    dash.main(["--out", str(self.out), "--no-gh", "--watch", "7"])
            except SystemExit:
                pass
        content = self.out.read_text()
        self.assertIn('content="7"', content)

    def test_watch_survives_render_error(self):
        import unittest.mock as mock
        ticks = [0]
        def fake_sleep(n):
            ticks[0] += 1
            if ticks[0] > 2:
                raise KeyboardInterrupt
        real = dash.read_jobs
        calls = [0]
        def flaky(d):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError("boom")
            return real(d)
        err = io.StringIO()
        with mock.patch.object(dash, "JOBS", self.jobs_dir), \
             mock.patch.object(dash, "CONFIG_PATH", self.root / "config.json"), \
             mock.patch.object(dash, "read_jobs", flaky), \
             mock.patch("time.sleep", fake_sleep), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            dash.main(["--out", str(self.out), "--no-gh", "--watch", "1"])
        self.assertEqual(calls[0], 3)
        self.assertIn("boom", err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
