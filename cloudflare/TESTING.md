# Preview smoke-test checklist

- [ ] `uv run pywrangler dev` starts without errors from cloudflare/
- [ ] `GET /` displays a clearly labelled migration-only page
- [ ] `GET /health` returns migration-preview, writes_enabled=false
- [ ] `GET /browse` returns 404 (not an empty production-looking archive)
- [ ] `GET /members/login` returns 404
- [ ] `GET /admin/members` returns 404
- [ ] `POST /members/register` does NOT create a record
- [ ] `POST /workprint/1/download` does NOT redirect
- [ ] No production database/files/credentials appear in GitHub or preview
- [ ] Cloudflare preview URL does not use production custom domain
- [ ] Main branch and Railway deployment still work as before

# Future acceptance gate before any production migration

- [ ] Reliable private backup of both SQLite DB and uploaded images
- [ ] D1 schema and data tested on a non-production database
- [ ] R2 images migrated and URL rendering tested
- [ ] Film, article, screenshot, member and history totals match backup
- [ ] Authentication and cookie security tested
- [ ] Admin CRUD, image upload/delete and contact inbox tested
- [ ] Rate limits and download quota race tests pass
- [ ] Sitemap, SEO, mobile rendering and HTTPS confirmed
- [ ] Rollback tested, final delta import and DNS cutover planned
