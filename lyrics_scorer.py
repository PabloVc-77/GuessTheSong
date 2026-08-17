"""
lyrics_scorer.py

Dynamic-programming alignment algorithm that scores a submitted lyric
fragment against the correct answer, choosing whichever valid alignment
maximizes the player's score (never assuming the first apparent
left-to-right alignment is best).

Core idea
---------
We walk two pointers forward:
    i -> position in self.answer_words   (source of truth)
    j -> position in normalized_words    (the submission)

together with a small piece of extra state:
    c -> current number of *consecutive* scoring errors

From any state (i, j, c) there are up to four possible "moves":

    A. correct match   -- normalized_words[j] == answer_words[i]
                           consumes both i and j, +1 point, c -> 0
    B. typo             -- normalized_words[j] != answer_words[i]
                           consumes both i and j, +0 points, c -> c+1
    C. omission          -- answer_words[i] was skipped entirely
                           consumes only i, +0 points, c -> c+1
    D. extra/error word -- normalized_words[j] doesn't belong here
                           consumes only j, +0 points, c -> c+1

If a move would push consecutive errors to MAX_CONSECUTIVE_ERRORS + 1,
the run is permanently broken from that point on: every submitted word
still left to analyze becomes a forced error with no further choices.

Because a given submitted word could plausibly be an error, a typo, or
the counterpart of an omission depending on what happens *later* in the
submission, a naive greedy/left-to-right scan can under-score a
transcript. We instead solve

    best(i, j, c) = max points obtainable from state (i, j, c) onward

with bottom-up dynamic programming, so every choice is made with full
knowledge of the best possible continuation, and we recover the actual
alignment (and its feedback) by replaying the recorded choices forward.

The DP guarantees the true maximum score. Ties (several alignments
reaching that same maximum score) are broken *lexicographically* using
exactly the priority order from the spec:

    1. score                       (already the primary DP objective)
    2. correct matches occurring earlier
    3. fewer total error events (errors + typos + omissions)
    4. fewer omissions
    5. prefer consuming a submitted word as a typo rather than
       discarding it as a plain extra/error, when otherwise equivalent

Rather than a single integer, every DP state therefore stores a small
5-tuple:

    (score, earliness_bonus, -error_events, -omissions, consumed_bonus)

Python compares tuples lexicographically out of the box, so taking the
`max()` of these tuples automatically applies criterion 2 only when
criterion 1 is tied, criterion 3 only when 1-2 are tied, and so on --
exactly the priority order above. Any transitions still tied after all
five components are considered are broken by a fixed, deterministic
evaluation order (correct, typo, omission, error), satisfying rule 6.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

# Index positions inside the 5-component tie-break value tuple.
_SCORE, _EARLY, _NEG_EVENTS, _NEG_OMIT, _CONSUMED = range(5)
_ZERO_VALUE: Tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)


def _add(a: Tuple[int, ...], b: Tuple[int, ...]) -> Tuple[int, ...]:
    return tuple(x + y for x, y in zip(a, b))


@dataclass
class FeedbackEntry:
    word: str
    correct: bool
    omitted: bool
    typo: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "correct": self.correct,
            "omitted": self.omitted,
            "typo": self.typo,
        }


class LyricsScorer:
    """
    Wraps `answer_words` (the source of truth) and exposes `score(...)`
    to evaluate a submitted, already-tokenized transcript.

    Matching is always done on the *normalized* tokens (lowercased,
    accent-stripped, etc.), but every feedback entry can report the
    original *display* form of a word instead -- useful when a game
    normalizes text for comparison but wants to show the player their
    own capitalization/accents back. Pass `answer_display_words` /
    `submitted_display_words` (index-aligned with the normalized lists)
    to opt into that; omit them and the normalized tokens are used
    as-is for display too.

    Usage:
        scorer = LyricsScorer(answer_words=["i", "want", "to", "love", "you"],
                               max_consecutive_errors=2)
        result = scorer.score(["i", "want", "love", "you"])
        result.score      -> int
        result.feedback   -> List[dict]
        result.broken     -> bool (hit the consecutive-error limit?)
    """

    def __init__(
        self,
        answer_words: List[str],
        max_consecutive_errors: int = 2,
        answer_display_words: Optional[List[str]] = None,
    ):
        self.answer_words = list(answer_words)
        self.answer_display_words = (
            list(answer_display_words)
            if answer_display_words is not None
            else list(answer_words)
        )
        self.MAX_CONSECUTIVE_ERRORS = max_consecutive_errors

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def score(
        self,
        normalized_words: List[str],
        submitted_display_words: Optional[List[str]] = None,
    ) -> "ScoreResult":
        answer = self.answer_words
        answer_display = self.answer_display_words
        submitted = list(normalized_words)
        submitted_display = (
            list(submitted_display_words)
            if submitted_display_words is not None
            else list(submitted)
        )
        N = len(answer)
        M = len(submitted)
        MAX = self.MAX_CONSECUTIVE_ERRORS

        # dp[i][j][c]     = best achievable (score, tie-break...) tuple
        #                   from this state onward
        # choice[i][j][c] = the move that attains it (for reconstruction)
        # c ranges 0..MAX (states where the run is still alive).
        dp: List[List[List[Tuple[int, int, int, int, int]]]] = [
            [[_ZERO_VALUE] * (MAX + 1) for _ in range(M + 1)] for _ in range(N + 1)
        ]
        choice: List[List[List[Optional[Tuple]]]] = [
            [[None] * (MAX + 1) for _ in range(M + 1)] for _ in range(N + 1)
        ]

        # Base case: j == M (submission exhausted) -> stop immediately,
        # no further score, no forced omissions for leftover answer words.
        # (dp[i][M][c] already initialized to the zero tuple above.)

        def tail_value(j_start: int) -> Tuple[int, int, int, int, int]:
            """Value of a permanently-broken tail: every remaining submitted
            word (from j_start to the end) becomes a forced plain error.
            Contributes only to the error-event count, nothing else."""
            forced = M - j_start
            return (0, 0, -forced, 0, 0)

        # Fill bottom-up: j descending, then i descending, so that every
        # state we need (i+1,j+1,*), (i+1,j,*), (i,j+1,*) is already done.
        for j in range(M - 1, -1, -1):
            for i in range(N, -1, -1):
                for c in range(0, MAX + 1):
                    candidates = []  # (value_tuple, move)  -- order = eval priority

                    # A. Correct match
                    if i < N and submitted[j] == answer[i]:
                        downstream = dp[i + 1][j + 1][0]
                        local = (1, -j, 0, 0, 0)
                        candidates.append((_add(local, downstream), ("correct", i, j)))

                    # B. Typo (token must actually differ): consumes the
                    # submitted word, pairs it with the omitted expected word.
                    if i < N and submitted[j] != answer[i]:
                        nc = c + 1
                        downstream = dp[i + 1][j + 1][nc] if nc <= MAX else tail_value(j + 1)
                        local = (0, 0, -1, -1, 1)
                        candidates.append((_add(local, downstream), ("typo", i, j, nc)))

                    # C. Omission (skip an answer word, no submitted word consumed)
                    if i < N:
                        nc = c + 1
                        downstream = dp[i + 1][j][nc] if nc <= MAX else tail_value(j)
                        local = (0, 0, -1, -1, 0)
                        candidates.append((_add(local, downstream), ("omission", i, nc)))

                    # D. Extra / error submitted word (discarded, unpaired)
                    nc = c + 1
                    downstream = dp[i][j + 1][nc] if nc <= MAX else tail_value(j + 1)
                    local = (0, 0, -1, 0, 0)
                    candidates.append((_add(local, downstream), ("error", j, nc)))

                    # max() keeps the FIRST candidate on an exact tie, so the
                    # fixed evaluation order above (correct, typo, omission,
                    # error) is the final, fully deterministic tie-break.
                    best_value, best_move = max(candidates, key=lambda cand: cand[0])

                    dp[i][j][c] = best_value
                    choice[i][j][c] = best_move

        total_score = dp[0][0][0][_SCORE]

        feedback, broken = self._reconstruct(
            answer_display, submitted_display, choice, MAX, i0=0, j0=0, c0=0, M=M
        )

        return ScoreResult(
            score=total_score,
            feedback=[f.as_dict() for f in feedback],
            broken=broken,
        )

    # ------------------------------------------------------------------ #
    # Internal: replay the recorded choices to build the feedback list.
    # Note: `choice` moves index into the *normalized* arrays, but the
    # words placed in feedback come from the *display* arrays passed in
    # here (which may be identical to the normalized ones by default).
    # ------------------------------------------------------------------ #
    @staticmethod
    def _reconstruct(
        answer_display: List[str],
        submitted_display: List[str],
        choice,
        MAX: int,
        i0: int,
        j0: int,
        c0: int,
        M: int,
    ) -> Tuple[List[FeedbackEntry], bool]:
        feedback: List[FeedbackEntry] = []
        i, j, c = i0, j0, c0
        broken = False

        while j < M:
            move = choice[i][j][c]
            kind = move[0]

            if kind == "correct":
                _, ci, cj = move
                feedback.append(
                    FeedbackEntry(submitted_display[cj], correct=True, omitted=False, typo=False)
                )
                i, j, c = ci + 1, cj + 1, 0

            elif kind == "typo":
                _, ci, cj, nc = move
                # 1. the omitted expected word, 2. the typo submission
                feedback.append(
                    FeedbackEntry(answer_display[ci], correct=False, omitted=True, typo=False)
                )
                feedback.append(
                    FeedbackEntry(submitted_display[cj], correct=False, omitted=False, typo=True)
                )
                if nc > MAX:
                    feedback.extend(
                        LyricsScorer._forced_errors(submitted_display, cj + 1, M)
                    )
                    broken = True
                    break
                i, j, c = ci + 1, cj + 1, nc

            elif kind == "omission":
                _, ci, nc = move
                feedback.append(
                    FeedbackEntry(answer_display[ci], correct=False, omitted=True, typo=False)
                )
                if nc > MAX:
                    feedback.extend(LyricsScorer._forced_errors(submitted_display, j, M))
                    broken = True
                    break
                i, c = ci + 1, nc

            elif kind == "error":
                _, cj, nc = move
                feedback.append(
                    FeedbackEntry(submitted_display[cj], correct=False, omitted=False, typo=False)
                )
                if nc > MAX:
                    feedback.extend(
                        LyricsScorer._forced_errors(submitted_display, cj + 1, M)
                    )
                    broken = True
                    break
                j, c = cj + 1, nc

            else:  # pragma: no cover - defensive
                raise RuntimeError(f"Unknown move kind: {kind!r}")

        return feedback, broken

    @staticmethod
    def _forced_errors(submitted_display: List[str], start: int, end: int) -> List[FeedbackEntry]:
        """Every submitted word left after a permanent break is an error."""
        return [
            FeedbackEntry(submitted_display[k], correct=False, omitted=False, typo=False)
            for k in range(start, end)
        ]


@dataclass
class ScoreResult:
    score: int
    feedback: List[Dict[str, Any]]
    broken: bool = False