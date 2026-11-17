# Rejected POSTs that sometimes never got their 401

*Area: local HTTP server (`webui.py`). Found during full-suite verification of milestone M2.*

## Symptom

A test that sends an unauthorised `POST` and expects `401 Unauthorized` failed now and then on
Windows with a connection reset instead of a response. It passed when run on its own, and it passed
most of the time in the full suite. Nothing in the handler was random.

## Reproducing it

Rather than add a retry to the test, a small local comparison was written: send the same rejected
`POST`, with a JSON body, 200 times against the server and count how many clients receive the
response. The original server produced **4 connection aborts in 200 requests**. An intermittent
failure became a number that could be measured before and after a change.

## Root cause

The server rejected the request (wrong Host, or missing token) *before reading its body*, wrote the
401 and closed the connection. The client's body was still sitting unread in the server's socket
receive buffer.

When a TCP socket is closed while received data is still unread, the stack may send `RST` instead
of a normal `FIN` (RFC 1122 §4.2.2.13 says a host *should* do this). A reset can make the client
discard data it has received but not yet read, so the 401 that was already sent is lost. Whether the
client reads the response before the reset arrives is a race, which is why it showed up only
sometimes, and more under the load of the full suite.

Successful requests never hit this, because the handler reads the body before replying.

## Fix

`Handler._discard_rejected_body` reads and throws away the rest of a rejected `POST` body before the
error response, so the socket closes cleanly:

- Only for `POST`, only when `Content-Length` is present and within the normal 1 MB body limit,
  and never for `Transfer-Encoding` bodies.
- At most one second in total, using the socket timeout, which is restored afterwards.
- The connection is always closed after a rejection, so an incomplete body can never be parsed as
  the next request.

With the fix, the same comparison returned **200 of 200** responses. No client retries or sleeps
were added.

## Regression tests

`tests/test_http_rejection.py`:

- a rejected `POST` has its body discarded before the response and is never dispatched to a route;
- the amount discarded is bounded;
- the timeout path restores the connection's previous settings;
- unauthorised `POST`s get a real response and leave the Library unchanged.

## Lessons

- An intermittent failure is a measurement problem first. Turning "sometimes" into "4 in 200"
  made it possible to tell whether a fix worked.
- Draining must be bounded. An unbounded drain would let anyone keep a connection busy by
  announcing a huge body; this one has a byte limit and a time limit.
- The cause was in the transport, not in authentication. Retrying in the test would have hidden a
  bug that real clients (the extension, the automation API) could hit.
