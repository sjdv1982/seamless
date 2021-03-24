
Cloudless roadmap
=================

Also see https://github.com/sjdv1982/seamless/blob/master/docs/developer/checksums.txt

  TODO: Need to implement snooping (over web socket).
graphID maps to:
  - template ctx.seamless + delta checksum dict,
    PLUS:
  - template status.seamless + delta checksum dict
  Templates are registered under service name (which also can import their .zip into Redis). Only admins can update templates (to update a service, or to update current graphs)
Internally, cloudless keeps graphID-to-Docker container mapping;
  - ports 5813, 5138 are mapped to ephemeral ports
  - Docker container is killed if there is no traffic for too long
  - Docker container is killed and re-launched if the graphID has its template changed. This should change index.html into something that asks for a refresh every few seconds (snooping connection should say this!)
  - new Docker container is launched if graphID receives traffic again
  - Docker containers are thin, all work is done in jobslave containers,
    communicate over communionserver
Finally, think of how to regulate:
- Docker image execution (esp Docker transformers) DONE
- Policy of whitelisting/forwarding certain transformer code checksums
- Authorization: use cookies with limited validity, bound to an IP address.
 OAuth is too complicated, ORCID isn't nice. Basic HTTP authentication has no expiry support.
For graphIDs created by anonymous users:
  - Create an anonymous long-lived cookie for seamless.rpbs.paris-univ-diderot.fr/graph/...
  - A website (e.g seamless.rpbs.paris-univ-diderot.fr/sesam/graphID=XYZ&cookie=...) will set the cookie,
    and redirect to seamless.rpbs.paris-univ-diderot.fr/graph/XYZ
For other graphIDs, the user cookie (after login) can also be the authorization. The user can disable or revoke
 anonymous cookies.
An authorization failure, by default, renders a screen where the user can ask a *new* graphID with the *same*
delta checksum dict. For the user, this feels as a read-only (to be more precise, a copy-on-write) view on the graph.
Docker containers could be launched as an ipykernel (e.g. using jupyter console) so that an admin can connect
 to it (notebooks cannot connect to an existing kernel, unfortunately; perhaps they could be launched from
 a notebook to begin with?). On the other hand, the graph data could simple be loaded by the admin in any context.


- Jobless: concept of eagerness (first-resort, last-resort backend)
  Make a jobless last-resort backend based on run-transformation. If needed, fire up database adapter on the fly.
