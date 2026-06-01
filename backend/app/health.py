from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Liveness probe.
    ---
    tags: [health]
    responses:
      200: {description: ok}
    """
    return jsonify(status="ok"), 200
