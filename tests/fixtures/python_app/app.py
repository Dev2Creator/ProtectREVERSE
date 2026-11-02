"""Tiny fixture app used by the test-suite. It is never executed by ProofGarden."""

from flask import Flask

from src.util import slugify

app = Flask(__name__)


@app.route("/")
def index():
    return "home"


@app.route("/items", methods=["GET", "POST"])
def items():
    return slugify("some items")
