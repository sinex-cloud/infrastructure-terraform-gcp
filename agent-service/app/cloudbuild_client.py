import logging

logger = logging.getLogger(__name__)


def trigger_review_build(pr_event: dict) -> None:
    # placeholder until cloudbuild/review.cloudbuild.yaml and its trigger exist
    logger.info("would trigger review build: %s", pr_event)
