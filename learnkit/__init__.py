"""learnkit: senses and method for an AI to learn from finished work that succeeded.

Not model training. A host (Claude through EditVideo's MCP server, or any other program) registers a finished work
(text, image, audio, web page, video…), attaches the evidence that it succeeded (platform metrics, analytics exports,
replay curves, sales, test results) against a baseline, and lets the caller label its parts. learnkit measures every
work and every part with the same senses, compares winners with controls, and keeps the caller's distilled blueprint
(structure, steps, measurable targets) behind evidence gates. A new work can then be measured against a blueprint, and
its real-world result logged, so a blueprint is only trusted after it worked again.

The core imports no host package. A host adds senses (EditVideo adds video) with `learnkit.senses.register`.
"""
__version__ = "0.1.0"
