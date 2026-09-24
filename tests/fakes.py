from GramAddict.core.storage import Storage


class InMemoryStore(Storage):
    """Storage without files: every *_path is None, so its writers skip the disk
    and all rules (following status, reinteract timing, queue) are the real ones."""

    def __init__(self, blacklist=(), whitelist=(), interacted_users=None):
        self.account_path = ""
        self.filter_path = ""
        self.report_path = ""
        self.interacted_users_path = None
        self.history_filter_users_path = None
        self.pending_replies_path = None
        self.source_positions_path = None
        self.interacted_users = dict(interacted_users or {})
        self.history_filter_users = {}
        self.pending_replies = []
        self.source_positions = {}
        self.blacklist = list(blacklist)
        self.whitelist = list(whitelist)
