/* 画面まわりの細かい動き。
   - 配車計算の待ち時間に出すローディング表示
   - 削除の確認ダイアログ
   - おでかけ作成での「選んだ運転手だけ集合時刻を出す」
   - トーストの自動消去とカードの表示アニメーション
   どれも無くても機能は成立するようにしてある（JSが動かなくても操作はできる）。 */
(function () {
    'use strict';

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------- ローディング（配車計算） ---------- */
    function setupLoader() {
        var loader = document.getElementById('loader');
        if (!loader) return;

        var steps = Array.prototype.slice.call(loader.querySelectorAll('.loader__step'));
        var bar = loader.querySelector('.loader__progress');
        var timers = [];

        function activate(index) {
            steps.forEach(function (step, i) {
                step.classList.toggle('is-done', i < index);
                step.classList.toggle('is-active', i === index);
            });
            if (bar) bar.style.width = ((index + 1) / steps.length * 90) + '%';
        }

        function show() {
            loader.hidden = false;
            document.body.style.overflow = 'hidden';
            activate(0);
            // 実際の進捗は取れないので、目安として段階的に進める。
            // 最後の段階はページが返るまで回したままにする。
            timers.push(setTimeout(function () { activate(1); }, 1400));
            timers.push(setTimeout(function () { activate(2); }, 4200));
        }

        document.addEventListener('click', function (e) {
            var trigger = e.target.closest('[data-loading]');
            if (!trigger || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            show();
        });

        // 「戻る」で戻ってきたときに出したままにしない
        window.addEventListener('pageshow', function (e) {
            if (e.persisted) {
                timers.forEach(clearTimeout);
                loader.hidden = true;
                document.body.style.overflow = '';
            }
        });
    }

    /* ---------- 削除の確認 ---------- */
    function setupConfirm() {
        var modal = document.getElementById('confirm');
        if (!modal) return;

        var titleEl = document.getElementById('confirm-title');
        var bodyEl = document.getElementById('confirm-body');
        var okBtn = document.getElementById('confirm-ok');
        var pending = null;
        var lastFocus = null;

        function close() {
            modal.hidden = true;
            pending = null;
            if (lastFocus) lastFocus.focus();
        }

        function open(form) {
            pending = form;
            lastFocus = document.activeElement;
            titleEl.textContent = form.dataset.confirmTitle || '削除しますか？';
            bodyEl.textContent = form.dataset.confirmBody || 'この操作は取り消せません。';
            modal.hidden = false;
            okBtn.focus();
        }

        document.addEventListener('submit', function (e) {
            var form = e.target;
            if (!form.hasAttribute('data-confirm') || form.dataset.confirmed === 'yes') return;
            e.preventDefault();
            open(form);
        });

        okBtn.addEventListener('click', function () {
            if (!pending) return;
            var form = pending;
            form.dataset.confirmed = 'yes';
            modal.hidden = true;
            pending = null;
            form.submit();
        });

        modal.querySelectorAll('[data-confirm-cancel]').forEach(function (el) {
            el.addEventListener('click', close);
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !modal.hidden) close();
        });
    }

    /* ---------- おでかけ作成フォーム ---------- */
    function setupRoundForm() {
        var form = document.getElementById('round-form');
        if (!form) return;

        var boxes = Array.prototype.slice.call(form.querySelectorAll('[data-member]'));
        var slots = Array.prototype.slice.call(form.querySelectorAll('.timeslot'));
        var summary = document.getElementById('pick-summary');
        var driverBlock = document.getElementById('driver-block');
        var driverEmpty = document.getElementById('driver-empty');

        function refresh(changedId) {
            var people = 0, cars = 0, seats = 0;

            boxes.forEach(function (box) {
                if (!box.checked) return;
                people += 1;
                if (box.dataset.hasCar === '1') {
                    cars += 1;
                    seats += parseInt(box.dataset.capacity || '0', 10);
                }
            });

            slots.forEach(function (slot) {
                var box = form.querySelector('[data-member][value="' + slot.dataset.driver + '"]');
                var on = !!(box && box.checked);
                if (on && slot.hidden) {
                    slot.hidden = false;
                    if (!reduceMotion && slot.dataset.driver === changedId) {
                        slot.classList.add('is-entering');
                        setTimeout(function () { slot.classList.remove('is-entering'); }, 320);
                    }
                } else if (!on) {
                    slot.hidden = true;
                    var input = slot.querySelector('input');
                    if (input) input.value = '';
                }
            });

            // 運転手が1人も登録されていなければ枠ごと隠す。
            // 登録はあるが誰も選ばれていないときは案内文に差し替える。
            if (driverBlock) driverBlock.hidden = slots.length === 0;
            if (driverEmpty) driverEmpty.hidden = cars > 0;

            if (summary) {
                var rest = Math.max(people - cars, 0);
                var free = Math.max(seats - cars, 0);
                summary.querySelector('[data-sum="people"]').textContent = people;
                summary.querySelector('[data-sum="cars"]').textContent = cars;
                summary.querySelector('[data-sum="seats"]').textContent = free;
                summary.classList.toggle('is-short', cars > 0 && rest > free);
                var warn = summary.querySelector('[data-sum="warn"]');
                if (warn) warn.hidden = !(cars > 0 && rest > free);
            }
        }

        boxes.forEach(function (box) {
            box.addEventListener('change', function () { refresh(box.value); });
        });
        refresh(null);
    }

    /* ---------- メンバー登録フォーム ---------- */
    function setupMemberForm() {
        var box = document.getElementById('has_car');
        var field = document.getElementById('capacity-field');
        if (!box || !field) return;

        // 定員は車を出す人にしか関係しないので、チェックしたときだけ出す
        function sync(animate) {
            if (box.checked) {
                field.hidden = false;
                if (animate && !reduceMotion) {
                    field.classList.add('is-entering');
                    setTimeout(function () { field.classList.remove('is-entering'); }, 320);
                }
            } else {
                field.hidden = true;
            }
        }

        box.addEventListener('change', function () { sync(true); });
        sync(false);
    }

    /* ---------- トースト ---------- */
    function setupToasts() {
        document.querySelectorAll('.toast').forEach(function (toast, i) {
            var close = toast.querySelector('.toast__close');
            function dismiss() {
                toast.classList.add('is-leaving');
                setTimeout(function () { toast.remove(); }, 260);
            }
            if (close) close.addEventListener('click', dismiss);
            setTimeout(dismiss, 4200 + i * 400);
        });
    }

    /* ---------- 表示アニメーション ---------- */
    function setupReveal() {
        var items = document.querySelectorAll('.reveal');
        if (!items.length) return;
        if (reduceMotion || !('IntersectionObserver' in window)) {
            items.forEach(function (el) { el.classList.add('is-in'); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                var el = entry.target;
                var delay = parseInt(el.dataset.delay || '0', 10);
                setTimeout(function () { el.classList.add('is-in'); }, delay);
                io.unobserve(el);
            });
        }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 });
        items.forEach(function (el) { io.observe(el); });
    }

    setupLoader();
    setupConfirm();
    setupRoundForm();
    setupMemberForm();
    setupToasts();
    setupReveal();
})();
