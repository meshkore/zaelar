#
# directory.py — the ADDRESS BOOK (V2-714): saved contacts, everyone he talks to, and the groups of the same walk.
#
from loguru import logger

from connectors.messaging import ingest
from connectors.telegram import service as _svc

#: Caps for one address-book pass. Telegram enumerates exactly, which is also how a single voice order
#: could turn into thousands of calls — the same reason `_drain_fetch` bounds its walk.
_MAX_DIALOGS = 200
_MAX_MEMBERS = 100


def _person(u, *, kind: str = "person") -> dict | None:
    """One Telegram user as the normalised row `widgets/contactos/imports.py` folds in."""
    if u is None or getattr(u, "bot", False):
        return None                          # a bot is not somebody in his address book
    name = " ".join(x for x in (getattr(u, "first_name", "") or "",
                                getattr(u, "last_name", "") or "") if x).strip()
    handle = str(getattr(u, "username", "") or "").strip()
    name = name or (f"@{handle}" if handle else "")
    if not name:
        return None                          # no name = unreferenceable; `merge_contacts` drops it anyway
    ch = {"platform": "telegram", "chatId": str(getattr(u, "id", "") or "")}
    if handle:
        ch["handle"] = f"@{handle}"
    row = {"name": name, "kind": kind, "channels": [ch],
           "externalIds": {"telegram": str(getattr(u, "id", "") or "")}}
    phone = str(getattr(u, "phone", "") or "").strip()
    if phone:
        # The PHONE is the key that makes this Iván and the Google Iván one person (`imports.phone_key`),
        # so it travels whenever Telegram gives it — which it does for saved contacts and not for strangers.
        row["phone"] = phone if phone.startswith("+") else f"+{phone}"
    return row


async def _drain_contacts() -> None:
    """Hand over the ADDRESS BOOK when the contacts widget asks (V2-714).

    Two halves, and both are needed. `GetContactsRequest` is the saved address book — «los tengo en mis
    contactos de Telegram», his words. `iter_dialogs` is everyone he actually TALKS to, saved or not, and
    that is the half that makes «escríbele a Iván» work for the people who matter most. Groups and channels
    come from the same walk, as `kind: "group"` rows with their members.

    A broadcast channel enumerates no members and says so (`membersKnown: false`): an empty list that means
    «we cannot know» must never look like one that means «nobody».
    """
    if _svc._contacts_inbox is None:
        return
    for _order in _svc._contacts_inbox.drain():
        people: dict[str, dict] = {}
        groups: list[dict] = []
        err = ""
        try:
            from telethon.tl.functions.contacts import GetContactsRequest
            got = await _svc._client(GetContactsRequest(hash=0))
            for u in getattr(got, "users", []) or []:
                row = _person(u)
                if row:
                    people[row["externalIds"]["telegram"]] = row
            async for dialog in _svc._client.iter_dialogs(limit=_MAX_DIALOGS):
                ent = dialog.entity
                if dialog.is_user:
                    row = _person(ent)
                    if row:
                        people.setdefault(row["externalIds"]["telegram"], row)
                    continue
                title = str(getattr(ent, "title", "") or "").strip()
                if not title:
                    continue
                broadcast = bool(dialog.is_channel and not dialog.is_group)
                members: list[dict] = []
                if not broadcast:
                    try:
                        for u in await _svc._client.get_participants(ent, limit=_MAX_MEMBERS):
                            row = _person(u)
                            if row:
                                members.append(row)
                                people.setdefault(row["externalIds"]["telegram"], row)
                    except Exception as e:  # noqa: BLE001
                        # Not being allowed to list a group's members is normal on Telegram and is not a
                        # failure of the pass: the GROUP still arrives, with the members we could see.
                        logger.debug(f"Telegram participants de «{title}»: {e}")
                groups.append({"name": title, "platform": "telegram",
                               "subtype": "channel" if broadcast else "group",
                               "externalIds": {"telegram": str(getattr(ent, "id", "") or "")},
                               "channels": [{"platform": "telegram",
                                             "chatId": str(getattr(ent, "id", "") or "")}],
                               "members": members})
        except Exception as e:  # noqa: BLE001
            err = f"Telegram no me dejó leer los contactos: {e}"
            logger.warning(err)
        ingest.publish_contacts("telegram", list(people.values()), groups, error=err)
        logger.info(f"Telegram contactos → {len(people)} personas, {len(groups)} grupos")
