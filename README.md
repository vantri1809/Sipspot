# SipSpot

The published site on `main` is a temporary “coming soon” holding page.

The full map site lives on the `full-site` branch. To put it back live on https://sipspot.co.uk:

```bash
git checkout main
git merge full-site
# or: git checkout main && git reset --hard full-site
git push origin main
```

The custom domain file `CNAME` (`sipspot.co.uk`) must stay on `main`.
