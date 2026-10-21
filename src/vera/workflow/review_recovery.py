from langgraph.checkpoint.sqlite import SqliteSaver

from vera.domain.review import ReviewStatus
from vera.workflow.review_service import ReviewService


def recover_reviews(saver: SqliteSaver, service: ReviewService) -> None:
    threads = {
        item.config["configurable"]["thread_id"]
        for item in saver.list(None)
    }
    for run_id in threads:
        snapshot = service.snapshot(run_id)
        record = service.reviews.get(run_id)
        if service.is_waiting(snapshot):
            if record is None:
                service.register(run_id)
            elif record.status == ReviewStatus.PROCESSING:
                decision = service.decisions.unfinished(run_id)
                if (
                    decision is not None
                    and decision.action == "revise"
                    and snapshot.values.get("revision_count", 0) > record.revision_count
                ):
                    revised = service.from_snapshot(
                        run_id,
                        version=record.version + 1,
                        history=[*record.feedback_history, decision.feedback or ""],
                    )
                    service.decisions.finish(decision, revised, revised)
                else:
                    service.reviews.set_error(
                        run_id, "Decision interrupted; retry with the same decision ID."
                    )
            continue
        if record is None:
            if (
                not snapshot.next
                and snapshot.values.get("run_id") == run_id
                and service.runtime.memory.get_run(run_id) is not None
            ):
                service.prune(run_id)
            continue
        if record.status == ReviewStatus.PROCESSING:
            decision = service.decisions.unfinished(run_id)
            saved = service.runtime.memory.get_run(run_id)
            if decision is not None and decision.action == "approve" and saved:
                service._approved(record, decision, saved)
            elif (
                decision is not None and decision.action == "reject"
                and snapshot.values.get("run_id") == run_id and not snapshot.next
            ):
                service._rejected(record, decision)
            else:
                service.reviews.set_error(
                    run_id, "Decision interrupted; retry with the same decision ID."
                )
        elif record.status in {ReviewStatus.APPROVED, ReviewStatus.REJECTED}:
            service.prune(run_id)
        elif record.status == ReviewStatus.PENDING:
            service.reviews.set_error(run_id, "Pending review checkpoint is unavailable.")

    for record in service.reviews.list_open():
        if (
            record.run_id not in threads
            and record.status in {ReviewStatus.PENDING, ReviewStatus.PROCESSING}
        ):
            service.reviews.set_error(record.run_id, "Review checkpoint is missing.")
