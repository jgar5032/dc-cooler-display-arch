pkgname=dc-cooler-display-arch
pkgver=0.2.1
pkgrel=3
pkgdesc='CPU temperature and usage monitor for compatible USB cooler displays'
arch=('any')
url='https://github.com/jgar5032/dc-cooler-display-arch'
license=('MIT')
depends=('python' 'systemd' 'gtk4' 'python-gobject' 'polkit')
provides=('cooler-display-monitor' 'deepcool-digital')
conflicts=('cooler-display-monitor' 'deepcool-digital')
install=deepcool-digital.install

# Build from a checkout with makepkg.
package() {
  cd "$startdir"
  local app_dir="$pkgdir/usr/lib/deepcool-digital"
  install -Dm755 deepcool-digital "$app_dir/deepcool-digital"
  install -Dm755 deepcool-digital-save-settings "$app_dir/deepcool-digital-save-settings"
  install -Dm644 -t "$app_dir/deepcool_digital" deepcool_digital/*.py
  install -dm755 "$pkgdir/usr/bin"
  ln -s "../lib/deepcool-digital/deepcool-digital" "$pkgdir/usr/bin/$pkgname"
  ln -s "$pkgname" "$pkgdir/usr/bin/cooler-display-monitor"
  ln -s "$pkgname" "$pkgdir/usr/bin/deepcool-digital"
  install -Dm644 packaging/deepcool-digital.service "$pkgdir/usr/lib/systemd/system/deepcool-digital.service"
  install -Dm644 packaging/70-deepcool-digital.rules "$pkgdir/usr/lib/udev/rules.d/70-deepcool-digital.rules"
  install -Dm644 packaging/sysusers.conf "$pkgdir/usr/lib/sysusers.d/deepcool-digital.conf"
  install -Dm644 packaging/tmpfiles.conf "$pkgdir/usr/lib/tmpfiles.d/deepcool-digital.conf"
  install -Dm644 packaging/io.github.jgar5032.DeepCoolDigital.desktop "$pkgdir/usr/share/applications/io.github.jgar5032.DeepCoolDigital.desktop"
  install -Dm644 packaging/io.github.jgar5032.DeepCoolDigital.policy "$pkgdir/usr/share/polkit-1/actions/io.github.jgar5032.DeepCoolDigital.policy"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
