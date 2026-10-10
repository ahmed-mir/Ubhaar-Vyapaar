# Production media storage

Marketplace listing images are public product/service marketing media. In
production, Django uses Cloudinary for the default media storage backend so
new uploaded listing images survive Render restarts and deploys.

Local development can continue to use the filesystem by setting
`DJANGO_DEBUG=True` and leaving `DJANGO_USE_CLOUDINARY_MEDIA` unset or false.

## Required production environment variables

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

## Optional environment variables

- `DJANGO_USE_CLOUDINARY_MEDIA=True` forces Cloudinary media storage and fails
  fast if credentials are missing. When unset, Cloudinary is enabled whenever
  `DJANGO_DEBUG=False`.
- `CLOUDINARY_MEDIA_PREFIX=marketplace` controls the Cloudinary public ID
  prefix for uploaded listing images.

Do not put Cloudinary credentials in `.env` for production commits. Configure
them only in the production environment.

## Public and private upload policy

Currently, the only upload field is `marketplace.CapacityListing.image`.
It represents public marketplace listing media and is safe to deliver through
public Cloudinary URLs.

The current schema does not contain KYC document uploads or other private file
fields. KYC status is stored as model data only. Future KYC/private document
uploads should use a separate private storage design and must not reuse this
public Cloudinary delivery path.

Existing local files are not automatically backfilled. If production already
has listing image rows pointing at files on local disk, migrate those assets to
Cloudinary before relying on this storage backend.
